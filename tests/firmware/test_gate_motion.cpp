#include <assert.h>
#include <stdint.h>
#include <stdio.h>

#include "gate_motion.h"

void test_full_open_and_close_take_three_seconds() {
  GateMotion motion(180, 25);
  assert(motion.angle() == 180);
  assert(!motion.update(100));
  motion.setTarget(60, 100);
  for (int step = 1; step <= 120; ++step) {
    uint32_t now = 100 + step * 25;
    assert(!motion.update(now - 1));
    assert(motion.update(now));
    assert(motion.angle() == 180 - step);
  }
  assert(motion.angle() == 60);
  assert(!motion.update(3101));
  motion.setTarget(180, 3100);
  for (int step = 1; step <= 120; ++step) {
    uint32_t now = 3100 + step * 25;
    assert(!motion.update(now - 1));
    assert(motion.update(now));
    assert(motion.angle() == 60 + step);
  }
  assert(motion.angle() == 180);
  assert(!motion.update(10000));
}

void test_reversal_starts_at_last_intermediate_angle() {
  GateMotion motion(180, 25);
  motion.setTarget(60, 0);
  for (uint32_t now = 25; now <= 250; now += 25) {
    assert(motion.update(now));
  }
  assert(motion.angle() == 170);
  motion.setTarget(180, 260);
  assert(motion.angle() == 170);
  assert(!motion.update(284));
  assert(motion.update(285));
  assert(motion.angle() == 171);
}

void test_repeated_target_does_not_postpone_motion() {
  GateMotion motion(180, 25);
  motion.setTarget(60, 0);
  for (uint32_t now = 1; now < 25; ++now) {
    motion.setTarget(60, now);
    assert(!motion.update(now));
  }
  motion.setTarget(60, 25);
  assert(motion.update(25));
  assert(motion.angle() == 179);
}

void test_current_angle_target_stops_motion() {
  GateMotion motion(180, 25);
  motion.setTarget(60, 0);
  assert(motion.update(25));
  motion.setTarget(179, 30);
  assert(!motion.update(1000));
  assert(motion.angle() == 179);
}

void test_delayed_updates_never_catch_up() {
  GateMotion motion(180, 25);
  motion.setTarget(60, 0);
  assert(motion.update(1000));
  assert(motion.angle() == 179);
  assert(!motion.update(1000));
  assert(!motion.update(1024));
  assert(motion.update(1025));
  assert(motion.angle() == 178);
}

void test_targets_are_clamped_and_never_overshot() {
  GateMotion motion(90, 25);
  motion.setTarget(-20, 0);
  for (uint32_t now = 25; now <= 2250; now += 25) {
    assert(motion.update(now));
  }
  assert(motion.angle() == 0);
  assert(!motion.update(3000));
  motion.setTarget(200, 3000);
  for (uint32_t now = 3025; now <= 7500; now += 25) {
    assert(motion.update(now));
  }
  assert(motion.angle() == 180);
  assert(!motion.update(8000));
}

void test_millis_rollover() {
  GateMotion motion(180, 25);
  motion.setTarget(60, UINT32_MAX - 10);
  assert(!motion.update(13));
  assert(motion.update(14));
  assert(motion.angle() == 179);
  assert(!motion.update(38));
  assert(motion.update(39));
  assert(motion.angle() == 178);
}

void test_slower_step_interval() {
  GateMotion motion(180, 40);
  motion.setTarget(60, 0);
  for (int step = 1; step <= 120; ++step) {
    uint32_t now = step * 40;
    assert(!motion.update(now - 1));
    assert(motion.update(now));
  }
  assert(motion.angle() == 60);
  assert(!motion.update(4801));
}

int main() {
  test_full_open_and_close_take_three_seconds();
  test_reversal_starts_at_last_intermediate_angle();
  test_repeated_target_does_not_postpone_motion();
  test_current_angle_target_stops_motion();
  test_delayed_updates_never_catch_up();
  test_targets_are_clamped_and_never_overshot();
  test_millis_rollover();
  test_slower_step_interval();
  puts("8 gate motion tests passed");
}
