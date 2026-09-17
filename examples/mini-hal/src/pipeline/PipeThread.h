#pragma once
#include <condition_variable>
#include <deque>
#include <functional>
#include <mutex>
#include <thread>

namespace halcam {

struct Frame;

// Worker thread that drains a frame queue. One PipeThread per RequestManager.
// enqueue() may be called from the framework thread; the handler runs on the worker thread.
class PipeThread {
public:
    using Handler = std::function<void(Frame &)>;

    explicit PipeThread(Handler handler);
    ~PipeThread();

    // Starts the worker. Safe to call once.
    void start();
    // Drains remaining frames and joins. Called from CameraDevice::close.
    void stop();
    // Pushes a frame for processing. Returns false when the thread is stopped.
    bool enqueue(Frame *frame);

private:
    void threadLoop();

    Handler handler_;
    std::thread thread_;
    std::mutex lock_;
    std::condition_variable cv_;
    std::deque<Frame *> queue_;
    bool running_ = false;
};

}  // namespace halcam
