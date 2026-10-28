"""Original seed content for the SkillTrack learning system."""

MODULE_TEMPLATES = (
    (
        "Foundations",
        "Build a safe, accurate understanding of the skill before increasing speed or complexity.",
        "Purpose and vocabulary",
        (
            "Start by naming the outcome you want from {skill}. A useful learning goal has "
            "three parts: a specific behavior, the conditions where it should happen, and a "
            "reasonable quality or safety limit. For example, instead of saying that you want "
            "to be good at {skill}, describe one small task you can complete reliably and the "
            "evidence that shows it is complete."
        ),
        "Safe routines and baselines",
        (
            "Create a short baseline before changing technique or speed. Record one or two "
            "observable details, stop when pain, confusion, or risk appears, and keep an "
            "appropriate first-aid or professional-safety boundary. For {skill}, a baseline "
            "should include what you did, what you observed, and what you want to improve next. "
            "Treat repeatable and safe effort as progress before chasing difficult outcomes."
        ),
    ),
    (
        "Build and Apply",
        "Turn the foundations into a repeatable practice cycle with useful feedback.",
        "Plan a focused practice",
        (
            "Choose one foundation detail that matters for {skill} and isolate it in a short "
            "practice set. Keep the environment controlled, use a simple plan, and avoid adding "
            "speed until the movement or result is consistently correct. A focused goal might be "
            "accuracy, timing, clarity, or a safe procedure rather than mere duration."
        ),
        "Observe and adjust",
        (
            "After practice, compare the intended result with the observed result. Look for one "
            "cause you can change rather than blaming the whole performance. For {skill}, useful "
            "feedback can come from a checklist, a trusted coach or mentor, a measured result, or "
            "a written reflection. Change only one important variable, then repeat to test it."
        ),
    ),
    (
        "Review and Transfer",
        "Check understanding and adapt the skill to realistic situations.",
        "Make decisions from evidence",
        (
            "A learner should not assume that an easy practice setting predicts success everywhere. "
            "For {skill}, compare different conditions, identify which constraints remain the "
            "same, and decide what must change. Separate a useful result from lucky success by "
            "looking for repeatability and an understandable reason."
        ),
        "Continue responsibly",
        (
            "Finish with a concise record: what you learned, what evidence supported it, and what "
            "you will practice next. In {skill}, schedule review before adding new difficulty, and "
            "know when to ask a qualified person for help. Continuous improvement means maintaining "
            "safe habits as the task becomes more demanding."
        ),
    ),
)

QUESTION_TEMPLATES = (
    (
        "beginner",
        "Which first goal is most useful when learning {skill}?",
        (
            "A precise behavior that can be observed and practiced safely",
            "Every advanced technique available",
            "As much speed as possible on the first attempt",
            "A goal based only on another learner's result",
        ),
        "a",
        "A precise, observable, and safely bounded goal gives the learner a clear starting point.",
    ),
    (
        "beginner",
        "What should you record in a baseline for {skill}?",
        (
            "The task, observable details, and stopping or risk limits",
            "Only the best possible result",
            "Other people's private information",
            "No information until an expert appears",
        ),
        "a",
        "A baseline should capture what happened and the safety boundaries used during practice.",
    ),
    (
        "intermediate",
        "What is the best next step when a practice result is not improving in {skill}?",
        (
            "Change every possible factor at once",
            "Ignore the poor result and practice harder",
            "Identify one important variable and test a focused adjustment",
            "Keep repeating the same action without a plan",
        ),
        "c",
        "Changing one important variable makes cause and effect easier to observe.",
    ),
    (
        "intermediate",
        "Which response best turns feedback about {skill} into useful learning?",
        (
            "Defend the original approach without checking evidence",
            "Compare the evidence with the goal and select one next adjustment",
            "Copy the loudest opinion without considering safety",
            "Skip review because feedback feels uncomfortable",
        ),
        "b",
        "Useful feedback is compared with a goal before a small, evidence-based adjustment is made.",
    ),
    (
        "challenge",
        "A familiar {skill} task now occurs under different time, resource, or environment constraints. What is the strongest response?",
        (
            "Apply the old routine unchanged even if it no longer fits",
            "Abort every task whenever a constraint appears",
            "Identify unchanged principles, assess the new risks, and adapt the plan safely",
            "Assume prior success guarantees the same result",
        ),
        "c",
        "Transfer requires keeping core principles while adapting deliberately to the new constraints.",
    ),
)

MODULE_FOCUS_QUESTIONS = (
    (
        "Foundation",
        "Which routine most directly supports a reliable foundation in {skill}?",
        (
            "Plan, perform within safety limits, observe evidence, and pause for review",
            "Skip preparation when the task looks simple",
            "Increase difficulty every time an error occurs",
            "Focus only on a final score",
        ),
        "a",
        "A repeated observe-plan-practice-review routine creates reliable learning.",
    ),
    (
        "Application",
        "Which action best demonstrates applying {skill} rather than just understanding it?",
        (
            "Memorize a list without using it",
            "Complete a controlled task and explain the evidence",
            "Describe the topic without trying a safe example",
            "Repeat instructions while avoiding feedback",
        ),
        "b",
        "Applied learning combines a completed task with understandable evidence.",
    ),
    (
        "Transfer",
        "Which plan best helps {skill} transfer to a new situation?",
        (
            "Keep every detail identical and ignore context",
            "Assume one successful result is enough",
            "Identify transferable principles and test them safely under new constraints",
            "Avoid all unfamiliar situations",
        ),
        "c",
        "Transfer comes from recognizing principles and testing them safely in changed conditions.",
    ),
)


def build_learning_seed(skill_names):
    """Build deterministic original content for three ordered modules per skill."""
    modules = []
    lessons = []
    questions = []

    for skill_name in skill_names:
        for module_index, (title, summary, lesson_title_1, lesson_body_1,
                           lesson_title_2, lesson_body_2) in enumerate(MODULE_TEMPLATES, 1):
            modules.append((skill_name, module_index, title, summary))

            lessons.extend([
                (
                    skill_name,
                    module_index,
                    1,
                    lesson_title_1,
                    lesson_body_1.format(skill=skill_name),
                ),
                (
                    skill_name,
                    module_index,
                    2,
                    lesson_title_2,
                    lesson_body_2.format(skill=skill_name),
                ),
            ])

            focus = MODULE_FOCUS_QUESTIONS[module_index - 1]
            focus_question = (
                focus[1].format(skill=skill_name),
                focus[2],
                focus[3],
                focus[4].format(skill=skill_name),
            )
            question_specs = [
                (
                    "beginner",
                    focus_question[0],
                    focus_question[1],
                    focus_question[2],
                    focus_question[3],
                )
            ]

            for difficulty, prompt, options, correct_option, explanation in QUESTION_TEMPLATES:
                if module_index == 1:
                    difficulty_override = difficulty
                elif module_index == 2:
                    difficulty_override = {
                        "beginner": "beginner",
                        "intermediate": "intermediate",
                        "challenge": "challenge",
                    }[difficulty]
                else:
                    difficulty_override = difficulty

                question_specs.append(
                    (
                        difficulty_override,
                        prompt.format(skill=skill_name),
                        tuple(option.format(skill=skill_name) for option in options),
                        correct_option,
                        explanation,
                    )
                )

            # Keep a single deterministic five-question sequence with two Beginner,
            # two Intermediate, and one Challenge item per module.
            question_specs = [
                question_specs[0],
                question_specs[1],
                question_specs[3],
                question_specs[4],
                question_specs[5],
            ]

            for question_index, (difficulty, prompt, options,
                                 correct_option, explanation) in enumerate(question_specs, 1):
                questions.append(
                    (
                        skill_name,
                        module_index,
                        question_index,
                        difficulty,
                        prompt,
                        options[0],
                        options[1],
                        options[2],
                        options[3],
                        correct_option,
                        explanation,
                    )
                )

    return modules, lessons, questions
