/*
 * FlipperPhunk — inline RS232 MitM relay.
 *
 * Two Flipper serial peripherals (hardware USART and LPUART) are wired,
 * through an external RS232 level shifter (see hardware/README.md), to the
 * two sides of a broken RS232 link. This app relays bytes between the two
 * sides in real time (so the link keeps working while it's plugged in),
 * shows a live view of both directions, logs everything to the SD card, and
 * can inject a canned byte sequence onto either side on demand.
 */
#include <furi.h>
#include <furi_hal_serial.h>
#include <furi_hal_serial_control.h>
#include <furi_hal_resources.h>

#include <gui/gui.h>
#include <gui/icon_animation.h>
#include <input/input.h>
#include <storage/storage.h>
#include <expansion/expansion.h>

#include <flipperphunk_icons.h>

#include <stdlib.h>
#include <string.h>
#include <stdio.h>

#define TAG "FlipperPhunk"

/* Side A = hardware USART, Flipper GPIO pins 13 (TX) / 14 (RX).
 * Side B = LPUART, Flipper GPIO pins 15 (TX) / 16 (RX).
 * See hardware/README.md for the level-shifter wiring these map to. */
#define SIDE_A_ID FuriHalSerialIdUsart
#define SIDE_B_ID FuriHalSerialIdLpuart

#define RX_STREAM_SIZE  2048
#define RELAY_CHUNK_MAX 64
#define PREVIEW_LEN     8 /* keeps the hex dump ("XX " * PREVIEW_LEN) on-screen at 128px wide */
#define LOG_DIR         EXT_PATH("apps_data/flipperphunk")

/* Byte sequence sent by the inject hotkey; edit to suit your target. */
static const uint8_t INJECT_PAYLOAD[] = {'\r', '\n'};

typedef enum {
    WorkerEvtStop = 1 << 0,
    WorkerEvtRxA = 1 << 1,
    WorkerEvtRxB = 1 << 2,
} WorkerEvtFlags;

#define WORKER_ALL_EVENTS (WorkerEvtStop | WorkerEvtRxA | WorkerEvtRxB)

typedef enum {
    AppStateSplash,
    AppStateSetup,
    AppStateRunning,
} AppState;

/* Startup mascot animation: shown alone (no operational data on screen
 * yet, since the relay hasn't started) for a short beat or until any key
 * is pressed, then dismissed for good. Never shown again during Setup or
 * Running so it can't compete with RELAYING/PAUSED/baud/counters/preview. */
#define SPLASH_DURATION_MS 1500

static const uint32_t kBaudRates[] = {
    1200,
    2400,
    4800,
    9600,
    19200,
    38400,
    57600,
    115200,
};
#define BAUD_COUNT (sizeof(kBaudRates) / sizeof(kBaudRates[0]))

typedef struct {
    ViewPort* view_port;
    Gui* gui;
    FuriMessageQueue* input_queue;

    Storage* storage;
    Expansion* expansion;

    AppState state;
    size_t baud_index;
    bool relay_paused;
    uint8_t inject_focus; /* 0 = side A, 1 = side B */

    IconAnimation* mascot;
    uint32_t splash_start_tick;

    FuriHalSerialHandle* handle_a;
    FuriHalSerialHandle* handle_b;
    FuriStreamBuffer* rx_stream_a;
    FuriStreamBuffer* rx_stream_b;
    FuriThread* worker;
    File* log_file;

    uint32_t bytes_a_to_b;
    uint32_t bytes_b_to_a;
    uint8_t preview_a[PREVIEW_LEN];
    uint8_t preview_b[PREVIEW_LEN];
    size_t preview_a_len;
    size_t preview_b_len;
} FlipperPhunkApp;

/* ---- serial RX callbacks (interrupt context: keep this tiny) ---- */

static void side_a_rx_callback(FuriHalSerialHandle* handle, FuriHalSerialRxEvent event, void* context) {
    FlipperPhunkApp* app = context;
    if(event & FuriHalSerialRxEventData) {
        uint8_t data = furi_hal_serial_async_rx(handle);
        furi_stream_buffer_send(app->rx_stream_a, &data, 1, 0);
        furi_thread_flags_set(furi_thread_get_id(app->worker), WorkerEvtRxA);
    }
}

static void side_b_rx_callback(FuriHalSerialHandle* handle, FuriHalSerialRxEvent event, void* context) {
    FlipperPhunkApp* app = context;
    if(event & FuriHalSerialRxEventData) {
        uint8_t data = furi_hal_serial_async_rx(handle);
        furi_stream_buffer_send(app->rx_stream_b, &data, 1, 0);
        furi_thread_flags_set(furi_thread_get_id(app->worker), WorkerEvtRxB);
    }
}

/* ---- logging ---- */

static void log_chunk(FlipperPhunkApp* app, char direction, const uint8_t* data, size_t len) {
    if(!app->log_file) return;
    char line[16 + RELAY_CHUNK_MAX * 3];
    int n = snprintf(line, sizeof(line), "%10lu %c ", (unsigned long)furi_get_tick(), direction);
    for(size_t i = 0; i < len && (size_t)n < sizeof(line) - 3; i++) {
        n += snprintf(line + n, sizeof(line) - n, "%02X ", data[i]);
    }
    if((size_t)n < sizeof(line) - 1) {
        line[n++] = '\n';
    }
    storage_file_write(app->log_file, line, n);
}

static void update_preview(uint8_t* preview, size_t* preview_len, const uint8_t* data, size_t len) {
    if(len >= PREVIEW_LEN) {
        memcpy(preview, data + (len - PREVIEW_LEN), PREVIEW_LEN);
        *preview_len = PREVIEW_LEN;
    } else {
        size_t keep = (*preview_len + len > PREVIEW_LEN) ? (PREVIEW_LEN - len) : *preview_len;
        size_t drop = *preview_len - keep;
        memmove(preview, preview + drop, keep);
        memcpy(preview + keep, data, len);
        *preview_len = keep + len;
    }
}

/* ---- relay worker thread ---- */

static int32_t relay_worker(void* context) {
    FlipperPhunkApp* app = context;
    uint8_t buf[RELAY_CHUNK_MAX];

    while(true) {
        uint32_t flags = furi_thread_flags_wait(WORKER_ALL_EVENTS, FuriFlagWaitAny, FuriWaitForever);
        if(flags & FuriFlagError) continue;
        if(flags & WorkerEvtStop) break;

        if(flags & WorkerEvtRxA) {
            size_t len;
            while((len = furi_stream_buffer_receive(app->rx_stream_a, buf, sizeof(buf), 0)) > 0) {
                app->bytes_a_to_b += len;
                update_preview(app->preview_a, &app->preview_a_len, buf, len);
                log_chunk(app, '>', buf, len);
                if(!app->relay_paused) {
                    furi_hal_serial_tx(app->handle_b, buf, len);
                }
            }
        }

        if(flags & WorkerEvtRxB) {
            size_t len;
            while((len = furi_stream_buffer_receive(app->rx_stream_b, buf, sizeof(buf), 0)) > 0) {
                app->bytes_b_to_a += len;
                update_preview(app->preview_b, &app->preview_b_len, buf, len);
                log_chunk(app, '<', buf, len);
                if(!app->relay_paused) {
                    furi_hal_serial_tx(app->handle_a, buf, len);
                }
            }
        }

        view_port_update(app->view_port);
    }

    return 0;
}

/* ---- relay start/stop ---- */

static bool relay_start(FlipperPhunkApp* app) {
    uint32_t baud = kBaudRates[app->baud_index];

    /* The expansion service also owns UART pins by default; release them
     * before we try to acquire the handles ourselves. */
    expansion_disable(app->expansion);

    app->handle_a = furi_hal_serial_control_acquire(SIDE_A_ID);
    app->handle_b = furi_hal_serial_control_acquire(SIDE_B_ID);
    if(!app->handle_a || !app->handle_b) {
        FURI_LOG_E(TAG, "Failed to acquire serial handles");
        if(app->handle_a) furi_hal_serial_control_release(app->handle_a);
        if(app->handle_b) furi_hal_serial_control_release(app->handle_b);
        app->handle_a = NULL;
        app->handle_b = NULL;
        expansion_enable(app->expansion);
        return false;
    }

    furi_hal_serial_init(app->handle_a, baud);
    furi_hal_serial_init(app->handle_b, baud);

    storage_simply_mkdir(app->storage, EXT_PATH("apps_data"));
    storage_simply_mkdir(app->storage, LOG_DIR);
    FuriString* path = furi_string_alloc();
    storage_get_next_filename(app->storage, LOG_DIR, "capture", ".log", path, 32);
    FuriString* full_path = furi_string_alloc_printf("%s/%s.log", LOG_DIR, furi_string_get_cstr(path));
    app->log_file = storage_file_alloc(app->storage);
    if(!storage_file_open(
           app->log_file, furi_string_get_cstr(full_path), FSAM_WRITE, FSOM_CREATE_ALWAYS)) {
        FURI_LOG_E(TAG, "Failed to open log file %s", furi_string_get_cstr(full_path));
        storage_file_free(app->log_file);
        app->log_file = NULL;
    }
    furi_string_free(path);
    furi_string_free(full_path);

    app->rx_stream_a = furi_stream_buffer_alloc(RX_STREAM_SIZE, 1);
    app->rx_stream_b = furi_stream_buffer_alloc(RX_STREAM_SIZE, 1);
    app->bytes_a_to_b = 0;
    app->bytes_b_to_a = 0;
    app->preview_a_len = 0;
    app->preview_b_len = 0;
    app->relay_paused = false;

    app->worker = furi_thread_alloc_ex("FlipperPhunkRelay", 1024, relay_worker, app);
    furi_thread_start(app->worker);

    furi_hal_serial_async_rx_start(app->handle_a, side_a_rx_callback, app, false);
    furi_hal_serial_async_rx_start(app->handle_b, side_b_rx_callback, app, false);

    return true;
}

static void relay_stop(FlipperPhunkApp* app) {
    if(app->handle_a) furi_hal_serial_async_rx_stop(app->handle_a);
    if(app->handle_b) furi_hal_serial_async_rx_stop(app->handle_b);

    if(app->worker) {
        furi_thread_flags_set(furi_thread_get_id(app->worker), WorkerEvtStop);
        furi_thread_join(app->worker);
        furi_thread_free(app->worker);
        app->worker = NULL;
    }

    if(app->handle_a) {
        furi_hal_serial_deinit(app->handle_a);
        furi_hal_serial_control_release(app->handle_a);
        app->handle_a = NULL;
    }
    if(app->handle_b) {
        furi_hal_serial_deinit(app->handle_b);
        furi_hal_serial_control_release(app->handle_b);
        app->handle_b = NULL;
    }

    expansion_enable(app->expansion);

    if(app->rx_stream_a) {
        furi_stream_buffer_free(app->rx_stream_a);
        app->rx_stream_a = NULL;
    }
    if(app->rx_stream_b) {
        furi_stream_buffer_free(app->rx_stream_b);
        app->rx_stream_b = NULL;
    }

    if(app->log_file) {
        storage_file_close(app->log_file);
        storage_file_free(app->log_file);
        app->log_file = NULL;
    }
}

/* ---- GUI ---- */

static void draw_hex_preview(Canvas* canvas, int32_t y, const uint8_t* data, size_t len) {
    char line[3 * PREVIEW_LEN + 1];
    size_t n = 0;
    for(size_t i = 0; i < len; i++) {
        n += snprintf(line + n, sizeof(line) - n, "%02X ", data[i]);
    }
    canvas_draw_str(canvas, 2, y, line);
}

static void draw_callback(Canvas* canvas, void* context) {
    FlipperPhunkApp* app = context;
    canvas_clear(canvas);
    canvas_set_font(canvas, FontPrimary);

    if(app->state == AppStateSplash) {
        /* Mascot is 40x40; center it horizontally, top-aligned, with the
         * title/hint text below. This screen shows nothing else, so the
         * animation can never obscure relay/traffic status. */
        canvas_draw_icon_animation(canvas, 44, 0, app->mascot);
        canvas_set_font(canvas, FontSecondary);
        canvas_draw_str_aligned(canvas, 64, 44, AlignCenter, AlignTop, "FlipperPhunk");
        canvas_draw_str_aligned(canvas, 64, 54, AlignCenter, AlignTop, "RS232 MitM");
    } else if(app->state == AppStateSetup) {
        canvas_draw_str(canvas, 2, 12, "FlipperPhunk RS232 MitM");
        canvas_set_font(canvas, FontSecondary);
        char buf[48];
        snprintf(buf, sizeof(buf), "Baud: %lu", (unsigned long)kBaudRates[app->baud_index]);
        canvas_draw_str(canvas, 2, 26, buf);
        canvas_draw_str(canvas, 2, 38, "Up/Down: change baud");
        canvas_draw_str(canvas, 2, 48, "OK: start relay");
        canvas_draw_str(canvas, 2, 58, "8N1 framing assumed");
    } else {
        char buf[48];
        canvas_draw_str(canvas, 2, 10, app->relay_paused ? "PAUSED" : "RELAYING");

        char focus[24];
        snprintf(focus, sizeof(focus), "Inject->%s", app->inject_focus == 0 ? "A" : "B");
        canvas_draw_str_aligned(canvas, 127, 7, AlignRight, AlignTop, focus);

        canvas_set_font(canvas, FontSecondary);
        snprintf(buf, sizeof(buf), "%lu baud", (unsigned long)kBaudRates[app->baud_index]);
        canvas_draw_str(canvas, 2, 20, buf);

        /* Side A traffic (relayed A->B) is "Phunk In"; Side B traffic
         * (relayed B->A) is "Phunk Out". Purely a UI label for the two
         * directional streams, not a claim about which side is "outside". */
        snprintf(buf, sizeof(buf), "Phunk In   %lu", (unsigned long)app->bytes_a_to_b);
        canvas_draw_str(canvas, 2, 31, buf);
        draw_hex_preview(canvas, 41, app->preview_a, app->preview_a_len);

        snprintf(buf, sizeof(buf), "Phunk Out  %lu", (unsigned long)app->bytes_b_to_a);
        canvas_draw_str(canvas, 2, 51, buf);
        draw_hex_preview(canvas, 61, app->preview_b, app->preview_b_len);
    }
}

static void input_callback(InputEvent* event, void* context) {
    FlipperPhunkApp* app = context;
    furi_message_queue_put(app->input_queue, event, 0);
}

/* IconAnimation advances its own frames off an internal timer; this just
 * asks the GUI to redraw when a new frame is ready. Runs on the GUI/timer
 * service, never on the relay worker or serial callbacks. */
static void mascot_update_callback(IconAnimation* instance, void* context) {
    UNUSED(instance);
    FlipperPhunkApp* app = context;
    view_port_update(app->view_port);
}

static void splash_dismiss(FlipperPhunkApp* app) {
    icon_animation_stop(app->mascot);
    app->state = AppStateSetup;
}

/* ---- app lifecycle ---- */

static FlipperPhunkApp* app_alloc(void) {
    FlipperPhunkApp* app = malloc(sizeof(FlipperPhunkApp));
    memset(app, 0, sizeof(FlipperPhunkApp));

    app->state = AppStateSplash;
    app->baud_index = 3; /* 9600 */
    app->inject_focus = 0;

    app->input_queue = furi_message_queue_alloc(8, sizeof(InputEvent));

    app->storage = furi_record_open(RECORD_STORAGE);
    app->expansion = furi_record_open(RECORD_EXPANSION);

    app->mascot = icon_animation_alloc(&A_Mascot_bop_40x40);
    icon_animation_set_update_callback(app->mascot, mascot_update_callback, app);

    app->view_port = view_port_alloc();
    view_port_draw_callback_set(app->view_port, draw_callback, app);
    view_port_input_callback_set(app->view_port, input_callback, app);

    app->gui = furi_record_open(RECORD_GUI);
    gui_add_view_port(app->gui, app->view_port, GuiLayerFullscreen);

    app->splash_start_tick = furi_get_tick();
    icon_animation_start(app->mascot);

    return app;
}

static void app_free(FlipperPhunkApp* app) {
    gui_remove_view_port(app->gui, app->view_port);
    furi_record_close(RECORD_GUI);
    view_port_free(app->view_port);

    icon_animation_free(app->mascot);

    furi_record_close(RECORD_EXPANSION);
    furi_record_close(RECORD_STORAGE);

    furi_message_queue_free(app->input_queue);
    free(app);
}

int32_t flipperphunk_app(void* p) {
    UNUSED(p);
    FlipperPhunkApp* app = app_alloc();

    bool running = true;
    InputEvent event;
    while(running) {
        FuriStatus status = furi_message_queue_get(app->input_queue, &event, 100);

        if(app->state == AppStateSplash) {
            /* Dismiss on any keypress, or automatically after the splash
             * duration elapses even with no input -- checked every poll
             * so it doesn't require a key event to fire. */
            bool key_pressed = status == FuriStatusOk &&
                                (event.type == InputTypeShort || event.type == InputTypeLong);
            bool timed_out =
                (furi_get_tick() - app->splash_start_tick) >= SPLASH_DURATION_MS;
            if(key_pressed || timed_out) {
                splash_dismiss(app);
                view_port_update(app->view_port);
            }
            continue;
        }

        if(status != FuriStatusOk) continue;
        if(event.type != InputTypeShort && event.type != InputTypeLong) continue;

        if(app->state == AppStateSetup) {
            if(event.key == InputKeyBack) {
                running = false;
            } else if(event.key == InputKeyUp) {
                app->baud_index = (app->baud_index + 1) % BAUD_COUNT;
            } else if(event.key == InputKeyDown) {
                app->baud_index = (app->baud_index + BAUD_COUNT - 1) % BAUD_COUNT;
            } else if(event.key == InputKeyOk) {
                if(relay_start(app)) {
                    app->state = AppStateRunning;
                }
            }
        } else {
            if(event.key == InputKeyBack) {
                relay_stop(app);
                app->state = AppStateSetup;
            } else if(event.key == InputKeyOk && event.type == InputTypeShort) {
                app->relay_paused = !app->relay_paused;
            } else if(event.key == InputKeyLeft && event.type == InputTypeShort) {
                app->inject_focus = 0;
            } else if(event.key == InputKeyRight && event.type == InputTypeShort) {
                app->inject_focus = 1;
            } else if(event.key == InputKeyOk && event.type == InputTypeLong) {
                FuriHalSerialHandle* target = app->inject_focus == 0 ? app->handle_a : app->handle_b;
                if(target) {
                    furi_hal_serial_tx(target, INJECT_PAYLOAD, sizeof(INJECT_PAYLOAD));
                    log_chunk(app, app->inject_focus == 0 ? 'i' : 'I', INJECT_PAYLOAD, sizeof(INJECT_PAYLOAD));
                }
            }
        }

        view_port_update(app->view_port);
    }

    if(app->state == AppStateRunning) {
        relay_stop(app);
    }
    app_free(app);
    return 0;
}
