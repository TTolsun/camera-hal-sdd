// Simplified HAL3 types for the mini-hal example. Real code includes <hardware/camera3.h>.
#pragma once
#include <cstdint>

typedef struct camera3_stream {
    int stream_type;
    uint32_t width;
    uint32_t height;
    int format;
} camera3_stream_t;

typedef struct camera3_stream_configuration {
    uint32_t num_streams;
    camera3_stream_t **streams;
    uint32_t operation_mode;
} camera3_stream_configuration_t;

typedef struct camera3_capture_request {
    uint32_t frame_number;
    const void *settings;
    uint32_t num_output_buffers;
} camera3_capture_request_t;

typedef struct camera3_capture_result {
    uint32_t frame_number;
    const void *result;
} camera3_capture_result_t;

// Framework callback table. HAL calls process_capture_result on completion.
typedef struct camera3_callback_ops {
    void (*process_capture_result)(const struct camera3_callback_ops *, const camera3_capture_result_t *);
} camera3_callback_ops_t;
