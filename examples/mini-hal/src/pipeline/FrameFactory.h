#pragma once
#include <memory>
#include <vector>
#include "hal3/types.h"
#include "pipeline/Frame.h"
#include "pipeline/Pipe.h"

namespace halcam {

// Builds a Frame for a capture request and owns the pipe chain that will process it.
// Concrete factories decide which pipes are attached (preview vs. still capture).
class FrameFactory {
public:
    virtual ~FrameFactory() = default;
    // Creates a frame for the request. The caller owns the returned frame.
    virtual std::unique_ptr<Frame> createFrame(const camera3_capture_request_t &request);
    // Runs every pipe in order. Stops at the first failing pipe.
    int runPipes(Frame &frame);

protected:
    // Subclasses fill pipes_ here. Called once from createFrame on first use.
    virtual void buildPipes() = 0;
    std::vector<std::unique_ptr<Pipe>> pipes_;
    bool built_ = false;
};

// Preview path: ISP only, low latency.
class PreviewFrameFactory : public FrameFactory {
protected:
    void buildPipes() override;
};

// Still capture path: ISP followed by SAT when the build enables it.
class CaptureFrameFactory : public FrameFactory {
public:
    std::unique_ptr<Frame> createFrame(const camera3_capture_request_t &request) override;
protected:
    void buildPipes() override;
};

}  // namespace halcam
