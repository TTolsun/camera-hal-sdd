#pragma once
#include <cstdint>
#include <memory>
#include <string>

namespace halcam {

struct Frame;

// One processing stage. Concrete pipes override process(). Ownership of the
// frame stays with the caller; a pipe never deletes a frame.
class Pipe {
public:
    explicit Pipe(std::string name) : name_(std::move(name)) {}
    virtual ~Pipe() = default;
    // Processes one frame in place. Returns 0 on success.
    virtual int process(Frame &frame) = 0;
    const std::string &name() const { return name_; }

protected:
    std::string name_;
};

// Image signal processor stage. Always present.
class IspPipe : public Pipe {
public:
    IspPipe() : Pipe("ISP") {}
    int process(Frame &frame) override;
};

#ifdef USE_SAT
// Spatial alignment transform stage for dual-camera fusion. Compiled only with -DUSE_SAT.
class SatPipe : public Pipe {
public:
    SatPipe() : Pipe("SAT") {}
    int process(Frame &frame) override;
private:
    int alignWithSecondary(Frame &frame);
};
#endif

}  // namespace halcam
