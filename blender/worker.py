"""Procedural MVP scene worker. Run by Blender, not by the API interpreter.

This worker intentionally uses a fixed set of operations and validated JSON. It
never evaluates Python supplied by an AI agent or API caller.
"""

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args(argv)


def material(name, color, roughness=0.65, metallic=0.0):
    mat = bpy.data.materials.new(name=name)
    mat.diffuse_color = (*color, 1.0)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return mat


def uv_sphere(name, location, scale, mat, parent=None):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=16, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.data.materials.append(mat)
    bpy.ops.object.shade_smooth()
    if parent:
        obj.parent = parent
        obj.location = location
    return obj


def cylinder(name, location, radius, depth, mat, vertices=32, radius_top=None):
    if radius_top is None:
        bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location)
    else:
        bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=radius, radius2=radius_top, depth=depth, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    bevel = obj.modifiers.new("Soft edges", "BEVEL")
    bevel.width = 0.06
    bevel.segments = 2
    obj.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
    return obj


def add_character(mats, frame_end):
    robe, gold, skin, dark = mats
    cylinder("Royal robe", (0, 0, 1.02), 0.74, 1.55, robe, radius_top=0.43)
    uv_sphere("Neck", (0, 0, 1.86), (0.22, 0.20, 0.24), skin)
    uv_sphere("Head", (0, 0, 2.22), (0.43, 0.38, 0.48), skin)
    uv_sphere("Hair", (0, 0.02, 2.53), (0.43, 0.37, 0.23), dark)
    # Stylized crown and a simple gold band.
    cylinder("Crown band", (0, 0, 2.66), 0.34, 0.14, gold)
    cylinder("Crown top", (0, 0, 2.82), 0.24, 0.22, gold, radius_top=0.12)
    uv_sphere("Crown jewel", (0, -0.255, 2.68), (0.07, 0.035, 0.08), skin)
    # Facial features face toward -Y, where the camera is located.
    for x in (-0.15, 0.15):
        uv_sphere("Eye", (x, -0.353, 2.27), (0.045, 0.035, 0.06), dark)
    uv_sphere("Nose", (0, -0.39, 2.17), (0.075, 0.07, 0.10), skin)
    cylinder("Sash", (0, -0.42, 1.18), 0.055, 0.92, gold, vertices=16)
    # Arm pivots make a small greeting motion possible without a full production rig.
    pivots = []
    for side in (-1, 1):
        pivot = bpy.data.objects.new("Arm pivot", None)
        bpy.context.collection.objects.link(pivot)
        pivot.location = (side * 0.43, 0, 1.68)
        sleeve = uv_sphere("Sleeve", (side * 0.30, 0, 0), (0.36, 0.18, 0.20), robe)
        sleeve.parent = pivot
        sleeve.location = (side * 0.30, 0, 0)
        hand = uv_sphere("Hand", (side * 0.58, -0.01, 0), (0.14, 0.12, 0.13), skin)
        hand.parent = pivot
        hand.location = (side * 0.58, -0.01, 0)
        pivots.append((side, pivot))
    for side, pivot in pivots:
        for frame, angle in ((1, 0.0), (frame_end // 3, 0.0), (frame_end // 2, 0.65 if side > 0 else -0.18), (frame_end * 2 // 3, 0.12 if side > 0 else 0.0), (frame_end, 0.0)):
            pivot.rotation_euler[1] = -angle if side > 0 else angle
            pivot.keyframe_insert(data_path="rotation_euler", frame=frame)
        if pivot.animation_data and pivot.animation_data.action:
            for fcurve in pivot.animation_data.action.fcurves:
                for key in fcurve.keyframe_points:
                    key.interpolation = "BEZIER"
    # Feet
    for x in (-0.25, 0.25):
        uv_sphere("Boot", (x, -0.07, 0.12), (0.20, 0.32, 0.12), dark)


def aim_at(obj, point):
    obj.rotation_euler = (Vector(point) - obj.location).to_track_quat("-Z", "Y").to_euler()


def main():
    args = parse_args()
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    scene = bpy.context.scene
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    robe = material("Royal crimson", (0.42, 0.025, 0.045), 0.48)
    gold = material("Warm gold", (0.75, 0.42, 0.08), 0.3, 0.55)
    skin = material("Warm skin", (0.72, 0.39, 0.23), 0.72)
    dark = material("Deep brown", (0.07, 0.035, 0.025), 0.8)
    floor_mat = material("Palace floor", (0.16, 0.09, 0.07), 0.82)
    wall_mat = material("Palace backdrop", (0.30, 0.12, 0.08), 0.9)

    cylinder("Floor", (0, 0, -0.08), 200, 0.15, floor_mat, vertices=64)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 2.6, 2.3))
    wall = bpy.context.object
    wall.name = "Backdrop"
    wall.dimensions = (12, 0.25, 5)
    wall.data.materials.append(wall_mat)
    # Simple stylized palace columns.
    for x in (-3.0, 3.0):
        cylinder("Palace column", (x, 1.8, 1.8), 0.22, 3.6, gold)
        cylinder("Column capital", (x, 1.8, 3.65), 0.38, 0.18, gold)

    duration = spec["scene"]["duration_seconds"]
    fps = spec["scene"]["fps"]
    frame_end = duration * fps
    add_character((robe, gold, skin, dark), frame_end)

    bpy.ops.object.camera_add(location=(0, -8.5, 2.75))
    camera = bpy.context.object
    camera.name = "Main Camera"
    camera.data.lens = 48
    aim_at(camera, (0, 0, 1.45))
    scene.camera = camera
    if spec["camera"]["movement"] == "slow_push_in":
        camera.location = (0, -9.2, 2.75)
        aim_at(camera, (0, 0, 1.45))
        camera.keyframe_insert(data_path="location", frame=1)
        camera.location = (0, -8.2, 2.75)
        camera.keyframe_insert(data_path="location", frame=frame_end)

    for name, location, energy, size in (
        ("Key light", (-3.5, -4.0, 6), 850, 4.0),
        ("Fill light", (3.5, -2.0, 3.5), 500, 3.0),
        ("Rim light", (0, 2.0, 4.5), 1000, 2.5),
    ):
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.name = name
        light.data.energy = energy
        light.data.shape = "DISK"
        light.data.size = size
        aim_at(light, (0, 0, 1.4))

    world = bpy.data.worlds.new("Warm studio world") if not bpy.data.worlds else bpy.data.worlds[0]
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.18, 0.18, 0.18, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.5

    width, height = spec["output"]["resolution"]
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items else "BLENDER_EEVEE"
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.fps = fps
    scene.frame_start = 1
    scene.frame_end = frame_end
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.filepath = str(Path(args.output).resolve())
    scene.render.image_settings.color_mode = "RGB"
    scene.view_settings.view_transform = "AgX" if "AgX" in scene.view_settings.bl_rna.properties["view_transform"].enum_items else "Standard"
    scene.frame_set(1)
    bpy.ops.render.render(animation=True)
    print(f"AI2Blender render complete: {args.output}")


if __name__ == "__main__":
    main()
