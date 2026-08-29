bl_info = {
    "name": "PJSK to TDA Auto Converter",
    "author": "hayasaka4042",
    "version": (1, 2, 0),
    "blender": (4, 2, 0),
    "location": "3D View > Sidebar > PJSK→TDA",
    "description": "依實際骨名與 Rest Matrix，將 PJSK/MMD Action 轉換到常見 TDA 骨架",
    "category": "Animation",
}

import hashlib
import math
import os
import re
import struct
import time
import traceback
import unicodedata

import bpy
from bpy.props import PointerProperty, StringProperty
from mathutils import Matrix, Vector


SOURCE_TEMPLATE_NAME = "PJSK_Source_Rig_TEMPLATE"
TEMPLATE_FILE = "pjsk_tda_rig_template.blend"
MATRIX_GATE = 1.0e-4
SCALE_GATE = 1.0e-5
LEG_IK_BONES = ("Knee_L", "Knee_R", "Ankle_L", "Ankle_R")

# This is the exact 62-bone output set from the user-approved full-song bake.
OUTPUT_BONES = (
    "ParentNode", "Center", "Groove", "Waist", "LowerBody", "UpperBody",
    "UpperBody2", "Leg_L", "Leg_R", "Neck", "Head", "Knee_L", "Knee_R",
    "Shoulder_L", "Shoulder_R", "Ankle_L", "Ankle_R", "Eyes", "Arm_L",
    "Arm_R", "LegTipEX_L", "LegTipEX_R", "ArmTwist_L", "ArmTwist_R",
    "Elbow_L", "Elbow_R", "HandTwist_L", "HandTwist_R", "Wrist_L",
    "Wrist_R", "Dummy_L", "Dummy_R", "IndexFinger1_L", "IndexFinger1_R",
    "LittleFinger1_L", "LittleFinger1_R", "MiddleFinger1_L",
    "MiddleFinger1_R", "RingFinger1_L", "RingFinger1_R", "Thumb0_L",
    "Thumb0_R", "IndexFinger2_L", "IndexFinger2_R", "LittleFinger2_L",
    "LittleFinger2_R", "MiddleFinger2_L", "MiddleFinger2_R", "RingFinger2_L",
    "RingFinger2_R", "Thumb1_L", "Thumb1_R", "IndexFinger3_L",
    "IndexFinger3_R", "LittleFinger3_L", "LittleFinger3_R",
    "MiddleFinger3_L", "MiddleFinger3_R", "RingFinger3_L", "RingFinger3_R",
    "Thumb2_L", "Thumb2_R",
)
OPTIONAL_BONES = frozenset(("Dummy_L", "Dummy_R"))


_BASE_BONE_ALIASES = {
    "ParentNode": ("全ての親", "AllParent", "MotherBone"),
    "Center": ("センター", "ｾﾝﾀｰ"),
    "Groove": ("グルーブ",),
    "Waist": ("腰",),
    "LowerBody": ("下半身",),
    "UpperBody": ("上半身",),
    "UpperBody2": ("上半身2", "上半身２"),
    "Neck": ("首",),
    "Head": ("頭",),
    "Eyes": ("両目",),
    "Leg_L": ("左足", "LeftLeg", "LegLeft"),
    "Leg_R": ("右足", "RightLeg", "LegRight"),
    "Knee_L": ("左ひざ", "左膝", "LeftKnee", "KneeLeft"),
    "Knee_R": ("右ひざ", "右膝", "RightKnee", "KneeRight"),
    "Shoulder_L": ("左肩", "LeftShoulder", "ShoulderLeft"),
    "Shoulder_R": ("右肩", "RightShoulder", "ShoulderRight"),
    "Ankle_L": ("左足首", "LeftAnkle", "AnkleLeft"),
    "Ankle_R": ("右足首", "RightAnkle", "AnkleRight"),
    "Arm_L": ("左腕", "LeftArm", "ArmLeft"),
    "Arm_R": ("右腕", "RightArm", "ArmRight"),
    "LegTipEX_L": ("左足先EX", "左つま先EX", "LeftLegTipEX", "LegTipEXLeft"),
    "LegTipEX_R": ("右足先EX", "右つま先EX", "RightLegTipEX", "LegTipEXRight"),
    "ArmTwist_L": ("左腕捩", "左腕捻", "LeftArmTwist", "ArmTwistLeft"),
    "ArmTwist_R": ("右腕捩", "右腕捻", "RightArmTwist", "ArmTwistRight"),
    "Elbow_L": ("左ひじ", "左肘", "LeftElbow", "ElbowLeft"),
    "Elbow_R": ("右ひじ", "右肘", "RightElbow", "ElbowRight"),
    "HandTwist_L": ("左手捩", "左手捻", "LeftHandTwist", "HandTwistLeft"),
    "HandTwist_R": ("右手捩", "右手捻", "RightHandTwist", "HandTwistRight"),
    "Wrist_L": ("左手首", "LeftWrist", "WristLeft"),
    "Wrist_R": ("右手首", "RightWrist", "WristRight"),
    "Dummy_L": ("左ダミー", "LeftDummy", "DummyLeft"),
    "Dummy_R": ("右ダミー", "RightDummy", "DummyRight"),
}


def _build_bone_aliases():
    aliases = {name: set(values) | {name} for name, values in _BASE_BONE_ALIASES.items()}
    finger_japanese = {
        "IndexFinger": ("人指", "人差指"),
        "LittleFinger": ("小指",),
        "MiddleFinger": ("中指",),
        "RingFinger": ("薬指",),
        "Thumb": ("親指",),
    }
    for canonical in OUTPUT_BONES:
        aliases.setdefault(canonical, {canonical})
        match = re.fullmatch(r"(IndexFinger|LittleFinger|MiddleFinger|RingFinger|Thumb)([0-3])_([LR])", canonical)
        if not match:
            continue
        finger, digit, side = match.groups()
        side_j = "左" if side == "L" else "右"
        side_e = "Left" if side == "L" else "Right"
        for finger_j in finger_japanese[finger]:
            aliases[canonical].add(f"{side_j}{finger_j}{digit}")
        aliases[canonical].add(f"{side_e}{finger}{digit}")
        aliases[canonical].add(f"{finger}{digit}{side_e}")
    return {name: tuple(sorted(values)) for name, values in aliases.items()}


BONE_ALIASES = _build_bone_aliases()

SOURCE_BONE_ALIASES = {
    "ControlNode": ("操作中心", "ControlNode"),
    "UpperBody1": ("上半身1", "上半身１", "UpperBody1"),
    "ShoulderP_L": ("左肩P", "ShoulderP_L"),
    "ShoulderP_R": ("右肩P", "ShoulderP_R"),
    "ShoulderC_L": ("左肩C", "ShoulderC_L"),
    "ShoulderC_R": ("右肩C", "ShoulderC_R"),
    "WaistCancel_L": ("腰キャンセル左", "WaistCancel_L"),
    "WaistCancel_R": ("腰キャンセル右", "WaistCancel_R"),
    "LegD_L": ("左足D", "LegD_L"),
    "LegD_R": ("右足D", "LegD_R"),
    "KneeD_L": ("左ひざD", "左膝D", "KneeD_L"),
    "KneeD_R": ("右ひざD", "右膝D", "KneeD_R"),
    "AnkleD_L": ("左足首D", "AnkleD_L"),
    "AnkleD_R": ("右足首D", "AnkleD_R"),
    "LegIKParent_L": ("左足IK親", "左足ＩＫ親", "LegIKParent_L"),
    "LegIKParent_R": ("右足IK親", "右足ＩＫ親", "LegIKParent_R"),
    "LegIK_L": ("左足IK", "左足ＩＫ", "LegIK_L"),
    "LegIK_R": ("右足IK", "右足ＩＫ", "LegIK_R"),
    "ToeTipIK_L": ("左つま先IK", "左つま先ＩＫ", "ToeTipIK_L"),
    "ToeTipIK_R": ("右つま先IK", "右つま先ＩＫ", "ToeTipIK_R"),
}


class ConversionError(RuntimeError):
    pass


def _matrix_error(a, b):
    return max(abs(a[row][col] - b[row][col]) for row in range(4) for col in range(4))


def _matrix_translation_error(a, b):
    return (a.translation - b.translation).length


def _action_digest(action):
    digest = hashlib.sha256()
    digest.update(action.name.encode("utf-8"))
    curves = sorted(action.fcurves, key=lambda fc: (fc.data_path, fc.array_index))
    for curve in curves:
        digest.update(curve.data_path.encode("utf-8"))
        digest.update(struct.pack("<i", curve.array_index))
        for key in curve.keyframe_points:
            digest.update(struct.pack("<dd", float(key.co.x), float(key.co.y)))
            digest.update(key.interpolation.encode("ascii"))
    return digest.hexdigest()


def _normalize_bone_name(value):
    value = unicodedata.normalize("NFKC", value or "").casefold()
    return "".join(character for character in value if character.isalnum())


def _mmd_names(pose_bone):
    mmd_bone = getattr(pose_bone, "mmd_bone", None)
    name_j = getattr(mmd_bone, "name_j", "") if mmd_bone else ""
    name_e = getattr(mmd_bone, "name_e", "") if mmd_bone else ""
    if not name_j:
        name_j = pose_bone.get("mmd_bone_name_j", pose_bone.get("name_j", ""))
    if not name_e:
        name_e = pose_bone.get("mmd_bone_name_e", pose_bone.get("name_e", ""))
    return str(name_j or ""), str(name_e or "")


def _resolve_bone_map(target):
    if target.type != "ARMATURE":
        raise ConversionError("目前選取物件不是骨架。")

    alias_sets = {
        canonical: {_normalize_bone_name(alias) for alias in aliases}
        for canonical, aliases in BONE_ALIASES.items()
    }
    alias_text_sets = {
        canonical: {unicodedata.normalize("NFKC", alias).casefold() for alias in aliases}
        for canonical, aliases in BONE_ALIASES.items()
    }
    mapping = {}
    mapping_sources = {}
    missing = []
    ambiguous = []

    for canonical in OUTPUT_BONES:
        candidates = []
        for pose_bone in target.pose.bones:
            name_j, name_e = _mmd_names(pose_bone)
            labels = (
                ("骨名", pose_bone.name),
                ("MMD日文名", name_j),
                ("MMD英文名", name_e),
            )
            best_score = None
            best_source = None
            for source, label in labels:
                normalized = _normalize_bone_name(label)
                if not normalized or normalized not in alias_sets[canonical]:
                    continue
                if source == "骨名" and label == canonical:
                    score = 0
                elif unicodedata.normalize("NFKC", label).casefold() in alias_text_sets[canonical]:
                    score = 1
                else:
                    score = 3
                if best_score is None or score < best_score:
                    best_score = score
                    best_source = source
            if best_score is not None:
                candidates.append((best_score, pose_bone.name, best_source))

        if not candidates:
            if canonical not in OPTIONAL_BONES:
                missing.append(canonical)
            continue
        best_score = min(item[0] for item in candidates)
        best = [item for item in candidates if item[0] == best_score]
        if len(best) != 1:
            ambiguous.append(f"{canonical}→{','.join(item[1] for item in best[:4])}")
            continue
        _score, actual_name, source = best[0]
        mapping[canonical] = actual_name
        mapping_sources[canonical] = source

    if missing:
        raise ConversionError("TDA 骨架缺少必要語意骨：" + ", ".join(missing))
    if ambiguous:
        raise ConversionError("TDA 骨名有歧義，禁止猜測：" + "; ".join(ambiguous))

    duplicate_actual = {}
    for canonical, actual_name in mapping.items():
        duplicate_actual.setdefault(actual_name, []).append(canonical)
    duplicate_actual = {
        actual_name: canonicals
        for actual_name, canonicals in duplicate_actual.items()
        if len(canonicals) > 1
    }
    if duplicate_actual:
        details = "; ".join(
            f"{actual_name}→{','.join(canonicals)}"
            for actual_name, canonicals in duplicate_actual.items()
        )
        raise ConversionError("同一骨骼被配對到多個語意，禁止轉換：" + details)
    return mapping, mapping_sources


def _mapped_output_bones(bone_map):
    return tuple(name for name in OUTPUT_BONES if name in bone_map)


def _leg_ik_constraints(obj, bone_map):
    result = []
    for canonical in LEG_IK_BONES:
        bone_name = bone_map[canonical]
        pose_bone = obj.pose.bones.get(bone_name)
        if pose_bone is None:
            raise ConversionError(f"目標缺少腿部骨骼：{canonical}（{bone_name}）")
        for constraint in pose_bone.constraints:
            if constraint.type == "IK" or constraint.name == "mmd_ik_limit_override":
                result.append((canonical, bone_name, constraint))
    return result


def _disable_leg_ik(obj, bone_map):
    constraints = _leg_ik_constraints(obj, bone_map)
    for _canonical, _bone_name, constraint in constraints:
        constraint.influence = 0.0
    active = [
        f"{canonical}({bone_name})/{constraint.name}={constraint.influence:g}"
        for canonical, bone_name, constraint in constraints
        if abs(float(constraint.influence)) > 1.0e-8
    ]
    if active:
        raise ConversionError("無法關閉腿部 IK：" + ", ".join(active))
    return len(constraints)


def _assert_leg_ik_off(obj, bone_map, frame):
    active = [
        f"{canonical}({bone_name})/{constraint.name}={constraint.influence:g}"
        for canonical, bone_name, constraint in _leg_ik_constraints(obj, bone_map)
        if abs(float(constraint.influence)) > 1.0e-8
    ]
    if active:
        raise ConversionError(
            f"腿部 IK 在 frame {frame} 被重新啟用：" + ", ".join(active)
        )


def _set_quaternion_modes(target, bone_map):
    changed = []
    for canonical in _mapped_output_bones(bone_map):
        pose_bone = target.pose.bones[bone_map[canonical]]
        if pose_bone.rotation_mode != "QUATERNION":
            changed.append((pose_bone, pose_bone.rotation_mode))
            pose_bone.rotation_mode = "QUATERNION"
    return changed


def _append_source_template(scene):
    path = os.path.join(os.path.dirname(__file__), TEMPLATE_FILE)
    if not os.path.isfile(path):
        raise ConversionError(f"找不到內建骨架模板：{path}")
    with bpy.data.libraries.load(path, link=False) as (data_from, data_to):
        if SOURCE_TEMPLATE_NAME not in data_from.objects:
            raise ConversionError(f"骨架模板缺少物件：{SOURCE_TEMPLATE_NAME}")
        data_to.objects = [SOURCE_TEMPLATE_NAME]
    source = data_to.objects[0]
    scene.collection.objects.link(source)
    source.hide_render = True
    source.hide_set(True)
    return source


def _remove_object(obj):
    if obj is None or obj.name not in bpy.data.objects:
        return
    data = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if data and data.users == 0 and data.name in bpy.data.armatures:
        bpy.data.armatures.remove(data)


def _escaped_bone_name(name):
    return name.replace("\\", "\\\\").replace('"', '\\"')


def _bone_data_path(name, suffix):
    return f'pose.bones["{_escaped_bone_name(name)}"].{suffix}'


def _source_alias_index(source):
    normalized = {}

    def add(alias, source_name):
        if source_name not in source.pose.bones:
            return
        key = _normalize_bone_name(alias)
        if key:
            normalized.setdefault(key, set()).add(source_name)

    for pose_bone in source.pose.bones:
        add(pose_bone.name, pose_bone.name)
    for canonical, aliases in BONE_ALIASES.items():
        for alias in aliases:
            add(alias, canonical)
    for source_name, aliases in SOURCE_BONE_ALIASES.items():
        for alias in aliases:
            add(alias, source_name)
    return normalized


def _resolve_target_source_map(source, target, bone_map):
    result = {actual: canonical for canonical, actual in bone_map.items()}
    normalized = _source_alias_index(source)
    for pose_bone in target.pose.bones:
        if pose_bone.name in result:
            continue
        if pose_bone.name in source.pose.bones:
            result[pose_bone.name] = pose_bone.name
            continue
        name_j, name_e = _mmd_names(pose_bone)
        candidates = set()
        for label in (pose_bone.name, name_j, name_e):
            candidates.update(normalized.get(_normalize_bone_name(label), set()))
        if len(candidates) == 1:
            result[pose_bone.name] = next(iter(candidates))
    return result


def _remap_source_action(source_action, source, target, bone_map):
    exact = {pose_bone.name: pose_bone.name for pose_bone in source.pose.bones}
    for canonical, actual_name in bone_map.items():
        exact[actual_name] = canonical

    normalized = _source_alias_index(source)

    def add_alias(alias, source_name):
        key = _normalize_bone_name(alias)
        if key and source_name in source.pose.bones:
            normalized.setdefault(key, set()).add(source_name)

    for canonical, actual_name in bone_map.items():
        add_alias(actual_name, canonical)
        pose_bone = target.pose.bones[actual_name]
        name_j, name_e = _mmd_names(pose_bone)
        add_alias(name_j, canonical)
        add_alias(name_e, canonical)

    remapped = 0
    unresolved = set()
    pattern = re.compile(r'^pose\.bones\["(.*)"\](\..+)$')
    for curve in source_action.fcurves:
        match = pattern.match(curve.data_path)
        if not match:
            continue
        action_bone_name, suffix = match.groups()
        source_name = exact.get(action_bone_name)
        if source_name is None:
            candidates = normalized.get(_normalize_bone_name(action_bone_name), set())
            if len(candidates) == 1:
                source_name = next(iter(candidates))
        if source_name is None:
            unresolved.add(action_bone_name)
            continue
        new_path = _bone_data_path(source_name, suffix[1:])
        if curve.data_path != new_path:
            curve.data_path = new_path
            remapped += 1
    return remapped, tuple(sorted(unresolved))


def _write_curve(action, data_path, array_index, group_name, frames, values):
    curve = action.fcurves.new(data_path, index=array_index, action_group=group_name)
    count = len(frames)
    curve.keyframe_points.add(count)
    coordinates = [0.0] * (count * 2)
    coordinates[0::2] = frames
    coordinates[1::2] = values
    curve.keyframe_points.foreach_set("co", coordinates)
    for point in curve.keyframe_points:
        point.interpolation = "LINEAR"
        point.handle_left_type = "AUTO_CLAMPED"
        point.handle_right_type = "AUTO_CLAMPED"
    curve.update()


def _make_action(name, frames, channels, bone_map):
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    try:
        for bone_name in _mapped_output_bones(bone_map):
            actual_name = bone_map[bone_name]
            loc_path = _bone_data_path(actual_name, "location")
            quat_path = _bone_data_path(actual_name, "rotation_quaternion")
            for index in range(3):
                _write_curve(action, loc_path, index, actual_name, frames, channels[bone_name]["loc"][index])
            for index in range(4):
                _write_curve(action, quat_path, index, actual_name, frames, channels[bone_name]["quat"][index])
        return action
    except Exception:
        bpy.data.actions.remove(action)
        raise


def _make_lower_action(name, frames, lower_channels, lower_body_name):
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    try:
        loc_path = _bone_data_path(lower_body_name, "location")
        quat_path = _bone_data_path(lower_body_name, "rotation_quaternion")
        for index in range(3):
            _write_curve(action, loc_path, index, lower_body_name, frames, lower_channels["loc"][index])
        for index in range(4):
            _write_curve(action, quat_path, index, lower_body_name, frames, lower_channels["quat"][index])
        return action
    except Exception:
        bpy.data.actions.remove(action)
        raise


def _capture_channels(context, source, target, frames, bone_map, target_source_map):
    channels = {
        name: {"loc": [[], [], []], "quat": [[], [], [], []]}
        for name in _mapped_output_bones(bone_map)
    }
    lower_channels = {"loc": [[], [], []], "quat": [[], [], [], []]}
    previous_quat = {}
    previous_lower_quat = None
    max_basis_scale_error = 0.0
    max_lower_matrix_error = 0.0
    worst_scale = (None, None)

    window_manager = context.window_manager
    for index, frame in enumerate(frames):
        context.scene.frame_set(frame)
        context.view_layer.update()

        source_pose = {bone.name: bone.matrix.copy() for bone in source.pose.bones}
        desired_pose = {}

        def desired_for(target_bone):
            cached = desired_pose.get(target_bone.name)
            if cached is not None:
                return cached
            source_name = target_source_map.get(target_bone.name)
            if source_name is not None:
                source_rest = source.data.bones[source_name].matrix_local
                desired = (
                    target_bone.matrix_local
                    @ source_rest.inverted()
                    @ source_pose[source_name]
                )
            elif target_bone.parent:
                parent_desired = desired_for(target_bone.parent)
                parent_rest = target_bone.parent.matrix_local
                desired = parent_desired @ parent_rest.inverted() @ target_bone.matrix_local
            else:
                desired = target_bone.matrix_local.copy()
            desired_pose[target_bone.name] = desired
            return desired

        for target_bone in target.data.bones:
            desired_for(target_bone)

        lower_matrix = source_pose["LowerBody"]
        lower_loc, lower_quat, lower_scale = lower_matrix.decompose()
        if previous_lower_quat is not None and previous_lower_quat.dot(lower_quat) < 0.0:
            lower_quat.negate()
        previous_lower_quat = lower_quat.copy()
        for component in range(3):
            lower_channels["loc"][component].append(float(lower_loc[component]))
        for component in range(4):
            lower_channels["quat"][component].append(float(lower_quat[component]))
        lower_rebuilt = Matrix.LocRotScale(lower_loc, lower_quat, Vector((1.0, 1.0, 1.0)))
        max_lower_matrix_error = max(max_lower_matrix_error, _matrix_error(lower_matrix, lower_rebuilt))

        for bone_name in _mapped_output_bones(bone_map):
            actual_name = bone_map[bone_name]
            target_bone = target.data.bones[actual_name]
            desired = desired_pose[actual_name]
            if target_bone.parent:
                parent_name = target_bone.parent.name
                if parent_name not in desired_pose:
                    raise ConversionError(
                        f"無法反解 {bone_name}（{actual_name}）：缺少父骨 {parent_name} 的姿勢。"
                    )
                basis = target_bone.convert_local_to_pose(
                    desired,
                    target_bone.matrix_local,
                    parent_matrix=desired_pose[parent_name],
                    parent_matrix_local=target_bone.parent.matrix_local,
                    invert=True,
                )
            else:
                basis = target_bone.convert_local_to_pose(
                    desired, target_bone.matrix_local, invert=True
                )

            loc, quat, scale = basis.decompose()
            scale_error = max(abs(float(component) - 1.0) for component in scale)
            if scale_error > max_basis_scale_error:
                max_basis_scale_error = scale_error
                worst_scale = (frame, f"{bone_name}({actual_name})")
            if bone_name in previous_quat and previous_quat[bone_name].dot(quat) < 0.0:
                quat.negate()
            previous_quat[bone_name] = quat.copy()
            for component in range(3):
                channels[bone_name]["loc"][component].append(float(loc[component]))
            for component in range(4):
                channels[bone_name]["quat"][component].append(float(quat[component]))

        window_manager.progress_update(index + 1)

    if max_basis_scale_error > SCALE_GATE:
        raise ConversionError(
            f"反解需要 scale（最大差 {max_basis_scale_error:.9g}，frame {worst_scale[0]}，"
            f"bone {worst_scale[1]}），已停止。"
        )
    return channels, lower_channels, max_basis_scale_error, max_lower_matrix_error


def _validate_result(context, source, target, output_action, frames, bone_map):
    target.animation_data_create()
    target.animation_data.action = output_action
    _disable_leg_ik(target, bone_map)
    max_matrix_error = 0.0
    max_translation_error = 0.0
    worst_matrix = (None, None)
    worst_translation = (None, None)
    window_manager = context.window_manager
    offset = len(frames)

    for index, frame in enumerate(frames):
        context.scene.frame_set(frame)
        context.view_layer.update()
        _assert_leg_ik_off(target, bone_map, frame)
        for bone_name in _mapped_output_bones(bone_map):
            source_bone = source.data.bones[bone_name]
            actual_name = bone_map[bone_name]
            target_bone = target.data.bones[actual_name]
            expected = (
                target_bone.matrix_local
                @ source_bone.matrix_local.inverted()
                @ source.pose.bones[bone_name].matrix
            )
            actual = target.pose.bones[actual_name].matrix
            matrix_error = _matrix_error(expected, actual)
            translation_error = _matrix_translation_error(expected, actual)
            if matrix_error > max_matrix_error:
                max_matrix_error = matrix_error
                worst_matrix = (frame, f"{bone_name}({actual_name})")
            if translation_error > max_translation_error:
                max_translation_error = translation_error
                worst_translation = (frame, f"{bone_name}({actual_name})")
        window_manager.progress_update(offset + index + 1)

    if max_matrix_error > MATRIX_GATE:
        raise ConversionError(
            f"輸出驗證失敗：矩陣差 {max_matrix_error:.9g} > {MATRIX_GATE:g} "
            f"（frame {worst_matrix[0]}，bone {worst_matrix[1]}）。"
        )
    return max_matrix_error, max_translation_error, worst_matrix, worst_translation


def _write_report(output_name, values):
    text_name = f"{output_name}_validation.txt"
    old = bpy.data.texts.get(text_name)
    if old:
        bpy.data.texts.remove(old)
    text = bpy.data.texts.new(text_name)
    text.write("PJSK → TDA Auto Converter\n")
    text.write("RESULT=PASS\n")
    for key, value in values.items():
        text.write(f"{key}={value}\n")
    return text


def convert_action(context, target, input_action, output_name):
    scene = context.scene
    frame_start = int(math.floor(input_action.frame_range[0]))
    frame_end = int(math.ceil(input_action.frame_range[1]))
    if frame_end < frame_start:
        raise ConversionError("Action 幀範圍無效。")
    frames = list(range(frame_start, frame_end + 1))
    lower_name = f"{output_name}_LowerBody_WORLD_BAKE"
    if bpy.data.actions.get(output_name):
        raise ConversionError(f"Action 已存在：{output_name}")
    if bpy.data.actions.get(lower_name):
        raise ConversionError(f"Action 已存在：{lower_name}")

    original_frame = scene.frame_current
    original_target_action = target.animation_data.action if target.animation_data else None
    input_digest_before = _action_digest(input_action)
    input_action.use_fake_user = True
    source = None
    source_action = None
    output_action = None
    lower_action = None
    bone_map = None
    original_leg_ik_influences = []
    original_rotation_modes = []
    start_time = time.monotonic()
    context.window_manager.progress_begin(0, len(frames) * 2)

    try:
        source = _append_source_template(scene)
        source.hide_set(False)
        source.matrix_world = target.matrix_world.copy()
        bone_map, mapping_sources = _resolve_bone_map(target)
        original_leg_ik_influences = [
            (constraint, float(constraint.influence))
            for _canonical, _bone_name, constraint in _leg_ik_constraints(target, bone_map)
        ]
        original_rotation_modes = _set_quaternion_modes(target, bone_map)
        disabled_leg_ik_constraints = _disable_leg_ik(target, bone_map)

        missing_source = [
            name for name in _mapped_output_bones(bone_map)
            if name not in source.pose.bones
        ]
        if missing_source:
            raise ConversionError("來源模板缺少輸出骨骼：" + ", ".join(missing_source))

        source_action = input_action.copy()
        source_action.name = f"__PJSK_SOURCE_{input_action.name}__"
        remapped_curves, unresolved_action_bones = _remap_source_action(
            source_action, source, target, bone_map
        )
        source.animation_data_create()
        source.animation_data.action = source_action

        target_source_map = _resolve_target_source_map(source, target, bone_map)
        channels, lower_channels, max_scale_error, max_lower_error = _capture_channels(
            context, source, target, frames, bone_map, target_source_map
        )
        lower_action = _make_lower_action(
            lower_name, frames, lower_channels, bone_map["LowerBody"]
        )
        output_action = _make_action(output_name, frames, channels, bone_map)

        max_matrix_error, max_translation_error, worst_matrix, worst_translation = _validate_result(
            context, source, target, output_action, frames, bone_map
        )
        input_digest_after = _action_digest(input_action)
        if input_digest_after != input_digest_before:
            raise ConversionError("來源 Action digest 改變；輸出已取消。")

        elapsed = time.monotonic() - start_time
        mapping_source_counts = {
            source_name: sum(1 for value in mapping_sources.values() if value == source_name)
            for source_name in ("骨名", "MMD日文名", "MMD英文名")
        }
        _write_report(output_name, {
            "input_action": input_action.name,
            "output_action": output_action.name,
            "lowerbody_world_bake": lower_action.name,
            "frames": f"{frame_start}-{frame_end}",
            "frame_count": len(frames),
            "output_bones": len(bone_map),
            "optional_bones_skipped": ",".join(
                name for name in OUTPUT_BONES if name not in bone_map
            ) or "NONE",
            "output_fcurves": len(output_action.fcurves),
            "output_keys": sum(len(fc.keyframe_points) for fc in output_action.fcurves),
            "source_digest_before": input_digest_before,
            "source_digest_after": input_digest_after,
            "target_rest_pose": "使用目標模型實際 Rest Matrix",
            "bone_mapping_count": len(bone_map),
            "hierarchy_bones_mapped": len(target_source_map),
            "bone_mapping_sources": ",".join(
                f"{key}:{value}" for key, value in mapping_source_counts.items()
            ),
            "bone_mapping": ";".join(
                f"{canonical}->{bone_map[canonical]}"
                for canonical in _mapped_output_bones(bone_map)
            ),
            "source_action_curves_remapped": remapped_curves,
            "source_action_unresolved_bones": ",".join(unresolved_action_bones) or "NONE",
            "max_lowerbody_matrix_error": max_lower_error,
            "max_output_matrix_error": max_matrix_error,
            "max_output_translation_error": max_translation_error,
            "worst_matrix_frame_bone": f"{worst_matrix[0]},{worst_matrix[1]}",
            "worst_translation_frame_bone": f"{worst_translation[0]},{worst_translation[1]}",
            "max_scale_deviation": max_scale_error,
            "scale_curves": 0,
            "ik_curves": 0,
            "leg_ik_state": "OFF",
            "leg_ik_constraints_disabled": disabled_leg_ik_constraints,
            "rotation_modes_changed_to_quaternion": len(original_rotation_modes),
            "elapsed_seconds": round(elapsed, 3),
        })
        target.animation_data.action = output_action
        return output_action, lower_action, max_matrix_error
    except Exception:
        if target.animation_data:
            target.animation_data.action = original_target_action
        for constraint, influence in original_leg_ik_influences:
            constraint.influence = influence
        for pose_bone, rotation_mode in original_rotation_modes:
            pose_bone.rotation_mode = rotation_mode
        for action in (output_action, lower_action):
            if action and action.name in bpy.data.actions:
                bpy.data.actions.remove(action)
        raise
    finally:
        context.window_manager.progress_end()
        scene.frame_set(original_frame)
        if source:
            if source.animation_data:
                source.animation_data.action = None
            _remove_object(source)
        if source_action and source_action.name in bpy.data.actions:
            bpy.data.actions.remove(source_action)


class PJSK_TDA_OT_convert(bpy.types.Operator):
    bl_idname = "pjsk_tda.convert_action"
    bl_label = "轉換所選 Action"
    bl_description = "用已驗證的 PJSK 來源骨架與靜置相對矩陣，烘焙成這支 TDA 模型的新 Action"

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"

    @staticmethod
    def _resolve_target(context):
        if context.object is not None and context.object.type == "ARMATURE":
            return context.object
        candidates = []
        for obj in context.scene.objects:
            if obj.type != "ARMATURE":
                continue
            try:
                _resolve_bone_map(obj)
            except ConversionError:
                continue
            candidates.append(obj)
        if len(candidates) == 1:
            return candidates[0]
        if not candidates:
            raise ConversionError("找不到具備必要語意骨的 TDA 骨架；請先匯入模型。")
        raise ConversionError("場景中有多個 TDA 骨架；請選取要轉換的骨架。")

    def execute(self, context):
        try:
            target = self._resolve_target(context)
        except ConversionError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        action = context.scene.pjsk_tda_input_action
        if action is None and target.animation_data:
            action = target.animation_data.action
        if action is None:
            self.report({"ERROR"}, "請先選擇輸入 Action。")
            return {"CANCELLED"}

        output_name = context.scene.pjsk_tda_output_name.strip()
        if not output_name:
            output_name = f"{action.name}_PJSK_TDA"
        try:
            output_action, lower_action, max_error = convert_action(
                context, target, action, output_name
            )
        except ConversionError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        except Exception as exc:
            traceback.print_exc()
            self.report({"ERROR"}, f"轉換失敗：{exc}")
            return {"CANCELLED"}

        self.report(
            {"INFO"},
            f"PASS：{output_action.name}；LowerBody={lower_action.name}；最大矩陣差={max_error:.3g}",
        )
        return {"FINISHED"}


class PJSK_TDA_PT_panel(bpy.types.Panel):
    bl_label = "PJSK → TDA"
    bl_idname = "PJSK_TDA_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "PJSK→TDA"

    def draw(self, context):
        layout = self.layout
        target = context.object
        if target and target.type == "ARMATURE":
            layout.label(text=f"目標：{target.name}", icon="ARMATURE_DATA")
        else:
            layout.label(text="未選取時會自動辨識場景唯一的相容 TDA", icon="INFO")
        layout.prop(context.scene, "pjsk_tda_input_action", text="輸入 Action")
        layout.prop(context.scene, "pjsk_tda_output_name", text="輸出名稱")
        layout.operator(PJSK_TDA_OT_convert.bl_idname, icon="ACTION")
        layout.separator()
        layout.label(text="支援常見英／日骨名與不同 Rest Pose", icon="CHECKMARK")
        layout.label(text="會自動關閉左右腿與腳尖 IK", icon="CHECKMARK")
        layout.label(text="原 Action 不會被修改")
        layout.label(text="不新增 IK／不建立 Scale 曲線")


CLASSES = (PJSK_TDA_OT_convert, PJSK_TDA_PT_panel)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.pjsk_tda_input_action = PointerProperty(
        name="輸入 Action",
        type=bpy.types.Action,
        description="要在 PJSK 相容來源骨架上運算的 Action",
    )
    bpy.types.Scene.pjsk_tda_output_name = StringProperty(
        name="輸出名稱",
        description="留空時自動使用 <輸入 Action>_PJSK_TDA",
        default="",
    )


def unregister():
    del bpy.types.Scene.pjsk_tda_output_name
    del bpy.types.Scene.pjsk_tda_input_action
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
