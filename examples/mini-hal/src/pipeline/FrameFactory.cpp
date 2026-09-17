#include "pipeline/FrameFactory.h"

namespace halcam {

std::unique_ptr<Frame> FrameFactory::createFrame(const camera3_capture_request_t &request) {
    if (!built_) {
        buildPipes();
        built_ = true;
    }
    auto frame = std::make_unique<Frame>();
    frame->frameNumber = request.frame_number;
    return frame;
}

int FrameFactory::runPipes(Frame &frame) {
    for (auto &pipe : pipes_) {
        int ret = pipe->process(frame);
        if (ret != 0) {
            return ret;
        }
    }
    return 0;
}

void PreviewFrameFactory::buildPipes() {
    pipes_.push_back(std::make_unique<IspPipe>());
}

std::unique_ptr<Frame> CaptureFrameFactory::createFrame(const camera3_capture_request_t &request) {
    auto frame = FrameFactory::createFrame(request);
    frame->isPreview = false;
    return frame;
}

void CaptureFrameFactory::buildPipes() {
    pipes_.push_back(std::make_unique<IspPipe>());
#ifdef USE_SAT
    pipes_.push_back(std::make_unique<SatPipe>());
#endif
}

}  // namespace halcam
