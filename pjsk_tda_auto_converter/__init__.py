bl_info = {
    "name": "PJSK to TDA Auto Converter",
    "author": "Codex",
    "version": (1, 1, 0),
    "blender": (4, 2, 0),
    "location": "3D View > Sidebar > PJSK→TDA",
    "description": "將 PJSK/MMD Action 依靜置姿勢相對矩陣轉換到已驗證的 TDA 初音骨架",
    "category": "Animation",
}

import hashlib
import math
import os
import struct
import time
import traceback

import bpy
from bpy.props import PointerProperty, StringProperty
from mathutils import Matrix, Vector


SOURCE_TEMPLATE_NAME = "PJSK_Source_Rig_TEMPLATE"
TARGET_TEMPLATE_NAME = "TDA_Target_Rig_TEMPLATE"
TEMPLATE_FILE = "pjsk_tda_rig_template.blend"
MATRIX_GATE = 1.0e-4
REST_GATE = 1.0e-5
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


def _constraint_signature(obj):
    result = []
    for pose_bone in obj.pose.bones:
        for constraint in pose_bone.constraints:
            target = getattr(constraint, "target", None)
            if target is obj:
                target_semantics = "SELF"
            elif target is None:
                target_semantics = None
            else:
                target_semantics = target.name
            result.append((
                pose_bone.name,
                constraint.name,
                constraint.type,
                target_semantics,
                getattr(constraint, "subtarget", ""),
                int(getattr(constraint, "chain_count", 0)),
            ))
    return tuple(sorted(result))


def _leg_ik_constraints(obj):
    result = []
    for bone_name in LEG_IK_BONES:
        pose_bone = obj.pose.bones.get(bone_name)
        if pose_bone is None:
            raise ConversionError(f"目標缺少腿部骨骼：{bone_name}")
        for constraint in pose_bone.constraints:
            if constraint.type == "IK" or constraint.name == "mmd_ik_limit_override":
                result.append((bone_name, constraint))
    if len(result) != 6:
        raise ConversionError(
            f"腿部 IK 結構不符：預期 6 個相關 Constraint，實際找到 {len(result)} 個。"
        )
    return result


def _disable_leg_ik(obj):
    constraints = _leg_ik_constraints(obj)
    for _bone_name, constraint in constraints:
        constraint.influence = 0.0
    active = [
        f"{bone_name}/{constraint.name}={constraint.influence:g}"
        for bone_name, constraint in constraints
        if abs(float(constraint.influence)) > 1.0e-8
    ]
    if active:
        raise ConversionError("無法關閉腿部 IK：" + ", ".join(active))
    return len(constraints)


def _assert_leg_ik_off(obj, frame):
    active = [
        f"{bone_name}/{constraint.name}={constraint.influence:g}"
        for bone_name, constraint in _leg_ik_constraints(obj)
        if abs(float(constraint.influence)) > 1.0e-8
    ]
    if active:
        raise ConversionError(
            f"腿部 IK 在 frame {frame} 被重新啟用：" + ", ".join(active)
        )


def _validate_target(target, template_target):
    if target.type != "ARMATURE":
        raise ConversionError("目前選取物件不是骨架。")

    missing = [bone.name for bone in template_target.data.bones if bone.name not in target.data.bones]
    if missing:
        raise ConversionError("目標不是已驗證的 TDA 骨架；缺少骨骼：" + ", ".join(missing[:8]))

    max_rest_error = 0.0
    wrong_parent = []
    for template_bone in template_target.data.bones:
        target_bone = target.data.bones[template_bone.name]
        template_parent = template_bone.parent.name if template_bone.parent else None
        target_parent = target_bone.parent.name if target_bone.parent else None
        if target_parent != template_parent:
            wrong_parent.append(template_bone.name)
        max_rest_error = max(
            max_rest_error,
            _matrix_error(target_bone.matrix_local, template_bone.matrix_local),
        )

    if wrong_parent:
        raise ConversionError("TDA 骨架父子關係不符：" + ", ".join(wrong_parent[:8]))
    if max_rest_error > REST_GATE:
        raise ConversionError(
            f"TDA rest matrix 不符（最大差 {max_rest_error:.9g} > {REST_GATE:g}）。"
        )
    if _constraint_signature(target) != _constraint_signature(template_target):
        raise ConversionError("TDA 既有 constraint 結構已變更；為避免錯誤烘焙已停止。")

    missing_output = [name for name in OUTPUT_BONES if name not in target.pose.bones]
    if missing_output:
        raise ConversionError("目標缺少輸出骨骼：" + ", ".join(missing_output))
    non_quaternion = [
        name for name in OUTPUT_BONES
        if target.pose.bones[name].rotation_mode != "QUATERNION"
    ]
    if non_quaternion:
        raise ConversionError("以下骨骼不是 Quaternion 模式：" + ", ".join(non_quaternion[:8]))
    return max_rest_error


def _append_templates(scene):
    path = os.path.join(os.path.dirname(__file__), TEMPLATE_FILE)
    if not os.path.isfile(path):
        raise ConversionError(f"找不到內建骨架模板：{path}")
    requested = (SOURCE_TEMPLATE_NAME, TARGET_TEMPLATE_NAME)
    with bpy.data.libraries.load(path, link=False) as (data_from, data_to):
        for name in requested:
            if name not in data_from.objects:
                raise ConversionError(f"骨架模板缺少物件：{name}")
        data_to.objects = list(requested)
    loaded = dict(zip(requested, data_to.objects))
    for obj in loaded.values():
        scene.collection.objects.link(obj)
        obj.hide_render = True
        obj.hide_set(True)
    return loaded[SOURCE_TEMPLATE_NAME], loaded[TARGET_TEMPLATE_NAME]


def _remove_object(obj):
    if obj is None or obj.name not in bpy.data.objects:
        return
    data = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if data and data.users == 0 and data.name in bpy.data.armatures:
        bpy.data.armatures.remove(data)


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


def _make_action(name, frames, channels):
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    try:
        for bone_name in OUTPUT_BONES:
            loc_path = f'pose.bones["{bone_name}"].location'
            quat_path = f'pose.bones["{bone_name}"].rotation_quaternion'
            for index in range(3):
                _write_curve(action, loc_path, index, bone_name, frames, channels[bone_name]["loc"][index])
            for index in range(4):
                _write_curve(action, quat_path, index, bone_name, frames, channels[bone_name]["quat"][index])
        return action
    except Exception:
        bpy.data.actions.remove(action)
        raise


def _make_lower_action(name, frames, lower_channels):
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    try:
        loc_path = 'pose.bones["LowerBody"].location'
        quat_path = 'pose.bones["LowerBody"].rotation_quaternion'
        for index in range(3):
            _write_curve(action, loc_path, index, "LowerBody", frames, lower_channels["loc"][index])
        for index in range(4):
            _write_curve(action, quat_path, index, "LowerBody", frames, lower_channels["quat"][index])
        return action
    except Exception:
        bpy.data.actions.remove(action)
        raise


def _capture_channels(context, source, target, frames):
    channels = {
        name: {"loc": [[], [], []], "quat": [[], [], [], []]}
        for name in OUTPUT_BONES
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
        for target_bone in target.data.bones:
            if target_bone.name in source_pose and target_bone.name in source.data.bones:
                source_rest = source.data.bones[target_bone.name].matrix_local
                desired_pose[target_bone.name] = (
                    target_bone.matrix_local @ source_rest.inverted() @ source_pose[target_bone.name]
                )

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

        for bone_name in OUTPUT_BONES:
            target_bone = target.data.bones[bone_name]
            desired = desired_pose[bone_name]
            if target_bone.parent:
                parent_name = target_bone.parent.name
                if parent_name not in desired_pose:
                    raise ConversionError(f"無法反解 {bone_name}：缺少父骨 {parent_name} 的來源姿勢。")
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
                worst_scale = (frame, bone_name)
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


def _validate_result(context, source, target, output_action, frames):
    target.animation_data_create()
    target.animation_data.action = output_action
    _disable_leg_ik(target)
    max_matrix_error = 0.0
    max_translation_error = 0.0
    worst_matrix = (None, None)
    worst_translation = (None, None)
    window_manager = context.window_manager
    offset = len(frames)

    for index, frame in enumerate(frames):
        context.scene.frame_set(frame)
        context.view_layer.update()
        _assert_leg_ik_off(target, frame)
        for bone_name in OUTPUT_BONES:
            source_bone = source.data.bones[bone_name]
            target_bone = target.data.bones[bone_name]
            expected = (
                target_bone.matrix_local
                @ source_bone.matrix_local.inverted()
                @ source.pose.bones[bone_name].matrix
            )
            actual = target.pose.bones[bone_name].matrix
            matrix_error = _matrix_error(expected, actual)
            translation_error = _matrix_translation_error(expected, actual)
            if matrix_error > max_matrix_error:
                max_matrix_error = matrix_error
                worst_matrix = (frame, bone_name)
            if translation_error > max_translation_error:
                max_translation_error = translation_error
                worst_translation = (frame, bone_name)
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
    template_target = None
    source_action = None
    output_action = None
    lower_action = None
    original_leg_ik_influences = [
        (constraint, float(constraint.influence))
        for _bone_name, constraint in _leg_ik_constraints(target)
    ]
    start_time = time.monotonic()
    context.window_manager.progress_begin(0, len(frames) * 2)

    try:
        source, template_target = _append_templates(scene)
        source.hide_set(False)
        source.matrix_world = target.matrix_world.copy()
        template_target.matrix_world = target.matrix_world.copy()
        disabled_leg_ik_constraints = _disable_leg_ik(target)
        max_rest_error = _validate_target(target, template_target)

        missing_source = [name for name in OUTPUT_BONES if name not in source.pose.bones]
        if missing_source:
            raise ConversionError("來源模板缺少輸出骨骼：" + ", ".join(missing_source))

        source_action = input_action.copy()
        source_action.name = f"__PJSK_SOURCE_{input_action.name}__"
        source.animation_data_create()
        source.animation_data.action = source_action

        channels, lower_channels, max_scale_error, max_lower_error = _capture_channels(
            context, source, target, frames
        )
        lower_action = _make_lower_action(lower_name, frames, lower_channels)
        output_action = _make_action(output_name, frames, channels)

        max_matrix_error, max_translation_error, worst_matrix, worst_translation = _validate_result(
            context, source, target, output_action, frames
        )
        input_digest_after = _action_digest(input_action)
        if input_digest_after != input_digest_before:
            raise ConversionError("來源 Action digest 改變；輸出已取消。")

        elapsed = time.monotonic() - start_time
        _write_report(output_name, {
            "input_action": input_action.name,
            "output_action": output_action.name,
            "lowerbody_world_bake": lower_action.name,
            "frames": f"{frame_start}-{frame_end}",
            "frame_count": len(frames),
            "output_bones": len(OUTPUT_BONES),
            "output_fcurves": len(output_action.fcurves),
            "output_keys": sum(len(fc.keyframe_points) for fc in output_action.fcurves),
            "source_digest_before": input_digest_before,
            "source_digest_after": input_digest_after,
            "max_rest_matrix_error": max_rest_error,
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
            "elapsed_seconds": round(elapsed, 3),
        })
        target.animation_data.action = output_action
        return output_action, lower_action, max_matrix_error
    except Exception:
        if target.animation_data:
            target.animation_data.action = original_target_action
        for constraint, influence in original_leg_ik_influences:
            constraint.influence = influence
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
        if template_target:
            _remove_object(template_target)
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
        candidates = [
            obj for obj in context.scene.objects
            if obj.type == "ARMATURE" and all(name in obj.pose.bones for name in OUTPUT_BONES)
        ]
        if len(candidates) == 1:
            return candidates[0]
        if not candidates:
            raise ConversionError("找不到可用的 TDA 骨架；請先匯入模型。")
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
            layout.label(text="未選取時會使用場景唯一的 TDA 骨架", icon="INFO")
        layout.prop(context.scene, "pjsk_tda_input_action", text="輸入 Action")
        layout.prop(context.scene, "pjsk_tda_output_name", text="輸出名稱")
        layout.operator(PJSK_TDA_OT_convert.bl_idname, icon="ACTION")
        layout.separator()
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
