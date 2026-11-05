import unittest

import main


class SkillCategoryTests(unittest.TestCase):
    def test_seed_contains_every_requested_skill_once(self):
        names = [name for _category, name in main.SKILL_SEED]

        self.assertEqual(len(names), 23)
        self.assertEqual(len(names), len(set(names)))

    def test_seed_categories_are_complete(self):
        categories = {
            category: [name for item_category, name in main.SKILL_SEED if item_category == category]
            for category in {
                "Sports & Physical Skills",
                "Coding & Digital Skills",
                "Everyday & Creative Skills",
            }
        }

        self.assertEqual(categories["Sports & Physical Skills"], [
            "Basketball", "Volleyball", "Badminton", "Football",
            "Running and Fitness", "Swimming", "Martial Arts", "Dance",
        ])
        self.assertEqual(categories["Coding & Digital Skills"], [
            "Python Programming", "HTML and CSS", "JavaScript",
            "Web Development", "Graphic Design", "Video Editing",
            "Basic Computer Skills",
        ])
        self.assertEqual(categories["Everyday & Creative Skills"], [
            "Cooking and Baking", "Drawing and Painting", "Photography",
            "Public Speaking", "Writing", "Basic Financial Literacy",
            "Gardening", "First Aid",
        ])


if __name__ == "__main__":
    unittest.main()
