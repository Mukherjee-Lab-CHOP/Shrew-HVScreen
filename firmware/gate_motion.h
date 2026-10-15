#ifndef GATE_MOTION_H
#define GATE_MOTION_H

#include <stdint.h>

class GateMotion {
 public:
  GateMotion(int initialDeg, uint32_t stepMs)
      : currentDeg_(initialDeg), targetDeg_(initialDeg),
        lastStepMs_(0), stepMs_(stepMs) {}

  void setTarget(int deg, uint32_t now) {
    if (deg < 0) deg = 0;
    if (deg > 180) deg = 180;
    if (deg == targetDeg_) return;
    targetDeg_ = deg;
    lastStepMs_ = now;
  }

  bool update(uint32_t now) {
    if (currentDeg_ == targetDeg_ || uint32_t(now - lastStepMs_) < stepMs_) {
      return false;
    }
    // Do not catch up after a delayed loop: that would produce an abrupt jump.
    currentDeg_ += targetDeg_ > currentDeg_ ? 1 : -1;
    lastStepMs_ = now;
    return true;
  }

  int angle() const { return currentDeg_; }

 private:
  int currentDeg_;
  int targetDeg_;
  uint32_t lastStepMs_;
  const uint32_t stepMs_;
};

#endif
