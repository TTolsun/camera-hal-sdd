#include "pipeline/PipeThread.h"
#include "pipeline/Frame.h"

namespace halcam {

PipeThread::PipeThread(Handler handler) : handler_(std::move(handler)) {}

PipeThread::~PipeThread() { stop(); }

void PipeThread::start() {
    std::lock_guard<std::mutex> guard(lock_);
    if (running_) return;
    running_ = true;
    thread_ = std::thread([this] { threadLoop(); });
}

void PipeThread::stop() {
    {
        std::lock_guard<std::mutex> guard(lock_);
        if (!running_) return;
        running_ = false;
    }
    cv_.notify_all();
    if (thread_.joinable()) thread_.join();
}

bool PipeThread::enqueue(Frame *frame) {
    std::lock_guard<std::mutex> guard(lock_);
    if (!running_) return false;
    queue_.push_back(frame);
    cv_.notify_one();
    return true;
}

void PipeThread::threadLoop() {
    while (true) {
        Frame *frame = nullptr;
        {
            std::unique_lock<std::mutex> guard(lock_);
            cv_.wait(guard, [this] { return !running_ || !queue_.empty(); });
            if (!running_ && queue_.empty()) return;
            frame = queue_.front();
            queue_.pop_front();
        }
        handler_(*frame);  // Runs on the worker thread.
    }
}

}  // namespace halcam
