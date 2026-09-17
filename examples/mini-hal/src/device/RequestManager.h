#pragma once
#include <map>
#include <memory>
#include <mutex>
#include "hal3/types.h"
#include "pipeline/Frame.h"
#include "pipeline/FrameFactory.h"
#include "pipeline/PipeThread.h"

namespace halcam {

// Owns in-flight frames between processCaptureRequest and the result callback.
// Frames are created here, processed on PipeThread, and released in onFrameDone.
class RequestManager {
public:
    RequestManager(const camera3_callback_ops_t *callbacks);
    ~RequestManager();

    // Picks a factory from the request, creates the frame and hands it to the worker.
    int submit(const camera3_capture_request_t &request);
    // Blocks until every in-flight frame has been returned.
    void drain();
    // Selects preview or capture path for a request.
    FrameFactory &selectFactory(const camera3_capture_request_t &request);

private:
    // Worker-thread handler: runs pipes then reports the result.
    void onFrame(Frame &frame);
    void onFrameDone(Frame &frame);
    void sendResult(const Frame &frame);

    const camera3_callback_ops_t *callbacks_;
    PreviewFrameFactory previewFactory_;
    CaptureFrameFactory captureFactory_;
    PipeThread thread_;
    std::mutex lock_;
    std::map<uint32_t, std::unique_ptr<Frame>> inFlight_;
};

}  // namespace halcam
