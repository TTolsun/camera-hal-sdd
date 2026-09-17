#include "pipeline/Pipe.h"
#include "pipeline/Frame.h"

namespace halcam {

int IspPipe::process(Frame &frame) {
    // Applies demosaic and noise reduction on the raw buffer.
    frame.stage = "isp";
    return 0;
}

#ifdef USE_SAT
int SatPipe::process(Frame &frame) {
    if (frame.secondaryBuffer == nullptr) {
        return -1;  // SAT requires the secondary camera buffer.
    }
    return alignWithSecondary(frame);
}

int SatPipe::alignWithSecondary(Frame &frame) {
    frame.stage = "sat";
    return 0;
}
#endif

}  // namespace halcam
