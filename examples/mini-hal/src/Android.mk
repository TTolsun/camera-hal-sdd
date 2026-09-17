# mini-hal: NDK-build 예제. ndk-build compile_commands.json 이 이 파일의 플래그로 compile DB 를 만든다.
LOCAL_PATH := $(call my-dir)
include $(CLEAR_VARS)
LOCAL_MODULE := camera.mini
LOCAL_CPPFLAGS := -std=c++17 -DUSE_SAT -DUSE_DUAL_CAMERA=0 -DMAX_PIPES=8
LOCAL_C_INCLUDES := $(LOCAL_PATH)
LOCAL_SRC_FILES := module/CameraModule.cpp device/CameraDevice.cpp device/RequestManager.cpp \
                   pipeline/FrameFactory.cpp pipeline/Pipe.cpp pipeline/PipeThread.cpp
include $(BUILD_SHARED_LIBRARY)
