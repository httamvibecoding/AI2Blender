import unittest

from backend.app.agent import plan_scene
from backend.app.schemas import SceneSpec


class ScenePlannerTests(unittest.TestCase):
    def test_plans_vietnamese_prompt_and_duration(self):
        result = plan_scene("Vua hoạt hình chào camera trong cung điện, 8 giây, camera tiến gần")
        spec = SceneSpec.model_validate(result["spec"])
        self.assertEqual(spec.scene.duration_seconds, 8)
        self.assertEqual(spec.camera.movement, "slow_push_in")
        self.assertEqual(spec.animation.action, "wave")

    def test_clamps_duration(self):
        result = plan_scene("King greeting for 99 seconds")
        spec = SceneSpec.model_validate(result["spec"])
        self.assertEqual(spec.scene.duration_seconds, 30)

    def test_unknown_scene_keys_are_rejected(self):
        with self.assertRaises(Exception):
            SceneSpec.model_validate({"run_python": "print('unsafe')"})


if __name__ == "__main__":
    unittest.main()
