"""Unit tests for the verb tool definitions (brain/tools.py).

Pure logic, no network. Verifies the schema is well-formed and all 17 verbs
are present with required fields.
"""

from brain.tools import VERBS, SYSTEM_PROMPT


class TestVerbSchema:
    def test_all_seventeen_verbs_present(self):
        names = {v["function"]["name"] for v in VERBS}
        assert names == {"forward", "backward", "turn", "stop", "speak",
                         "get_obstacles", "get_state",
                         "get_temperature", "get_audio", "get_gyro",
                         "get_distance",
                         "look_around", "check_map", "check_safety",
                         "search_knowledge", "log_finding", "analyze_patterns"}

    def test_each_verb_has_type_function(self):
        for verb in VERBS:
            assert verb["type"] == "function"
            assert "function" in verb
            assert "name" in verb["function"]
            assert "description" in verb["function"]

    def test_each_verb_has_parameters(self):
        for verb in VERBS:
            assert "parameters" in verb["function"]
            assert verb["function"]["parameters"]["type"] == "object"

    def test_forward_requires_distance_m(self):
        forward = next(v for v in VERBS if v["function"]["name"] == "forward")
        assert "distance_m" in forward["function"]["parameters"]["properties"]
        assert forward["function"]["parameters"]["required"] == ["distance_m"]

    def test_turn_requires_degrees(self):
        turn = next(v for v in VERBS if v["function"]["name"] == "turn")
        assert "degrees" in turn["function"]["parameters"]["properties"]
        assert turn["function"]["parameters"]["required"] == ["degrees"]

    def test_speak_requires_text(self):
        speak = next(v for v in VERBS if v["function"]["name"] == "speak")
        assert "text" in speak["function"]["parameters"]["properties"]
        assert speak["function"]["parameters"]["required"] == ["text"]

    def test_stop_has_no_required_params(self):
        stop = next(v for v in VERBS if v["function"]["name"] == "stop")
        assert stop["function"]["parameters"].get("required", []) == []

    def test_get_obstacles_has_no_required_params(self):
        get_obs = next(v for v in VERBS if v["function"]["name"] == "get_obstacles")
        assert get_obs["function"]["parameters"].get("required", []) == []

    def test_get_state_has_no_required_params(self):
        get_state = next(v for v in VERBS if v["function"]["name"] == "get_state")
        assert get_state["function"]["parameters"].get("required", []) == []


class TestSystemPrompt:
    def test_prompt_mentions_rescue_rover(self):
        assert "rescue rover" in SYSTEM_PROMPT.lower()

    def test_prompt_mentions_verbs(self):
        assert "forward" in SYSTEM_PROMPT
        assert "speak" in SYSTEM_PROMPT

    def test_prompt_is_nonempty(self):
        assert len(SYSTEM_PROMPT) > 100
