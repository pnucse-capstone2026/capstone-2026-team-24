SAFE_LIMITS = {
    "shoulder_pan.pos":  (-91.0, 87.0),
    "shoulder_lift.pos": (-93.0, 82.0),
    "elbow_flex.pos":    (-79.0, 79.5),
    "wrist_flex.pos":    (-11.0, 81.0),
    "wrist_roll.pos":    (-82.0, 63.5),
    "gripper.pos":       (0.0, 95.0),
}

MAX_DELTA_PER_STEP = {
    "shoulder_pan.pos": 15.0,
    "shoulder_lift.pos": 15.0,
    "elbow_flex.pos": 15.0,
    "wrist_flex.pos": 15.0,
    "wrist_roll.pos": 15.0,
    "gripper.pos": 20.0,
}

def apply_safety_limits(action_dict, previous_action_dict):
    safe_action = {}
    for key, value in action_dict.items():
        min_v, max_v = SAFE_LIMITS.get(key, (None, None))
        if min_v is not None:
            value = max(value, min_v)
        if max_v is not None:
            value = min(value, max_v)
        if previous_action_dict is not None and key in previous_action_dict:
            prev_value = previous_action_dict[key]
            max_delta = MAX_DELTA_PER_STEP.get(key, None)
            if max_delta is not None:
                delta = value - prev_value
                if abs(delta) > max_delta:
                    value = prev_value + max_delta * (1 if delta > 0 else -1)
        safe_action[key] = value
    return safe_action

# 테스트
action1 = {'shoulder_lift.pos': -50.0, 'elbow_flex.pos': 30.0, 'gripper.pos': 50.0}
result1 = apply_safety_limits(action1, None)
print('케이스1 (정상값):', result1)

action2 = {'shoulder_lift.pos': -150.0, 'elbow_flex.pos': 200.0, 'gripper.pos': 50.0}
result2 = apply_safety_limits(action2, None)
print('케이스2 (범위 초과, clip):', result2)

prev = {'shoulder_lift.pos': 0.0, 'elbow_flex.pos': 0.0, 'gripper.pos': 50.0}
action3 = {'shoulder_lift.pos': -80.0, 'elbow_flex.pos': 50.0, 'gripper.pos': 50.0}
result3 = apply_safety_limits(action3, prev)
print('케이스3 (급격한 변화, delta 제한):', result3)
