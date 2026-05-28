from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from xml_profile_extractor import extract_path, profile_to_copilot_prefill


class XmlProfileExtractorTests(unittest.TestCase):
    def test_extracts_core_rows_and_copilot_prefill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Game.xml").write_text(
                """<?xml version="1.0" encoding="utf-8"?>
<GameData>
  <Civilizations><Row CivilizationType="CIVILIZATION_TEST" Name="LOC_CIV_TEST_NAME" Adjective="LOC_CIV_TEST_ADJ"/></Civilizations>
  <Leaders><Row LeaderType="LEADER_TEST" Name="LOC_LEADER_TEST_NAME"/></Leaders>
  <CivilizationLeaders><Row CivilizationType="CIVILIZATION_TEST" LeaderType="LEADER_TEST"/></CivilizationLeaders>
  <Units><Row UnitType="UNIT_TEST" Name="LOC_UNIT_TEST_NAME"/></Units>
  <Modifiers><Update><Where ModifierId="OLD"/><Set ModifierId="NEW"/></Update></Modifiers>
</GameData>
""",
                encoding="utf-8",
            )
            (root / "Text.xml").write_text(
                """<BaseGameText>
  <Row Tag="LOC_CIV_TEST_NAME"><Text>Test Civ</Text></Row>
  <Row Tag="LOC_CIV_TEST_ADJ"><Text>Testian</Text></Row>
  <Row Tag="LOC_LEADER_TEST_NAME"><Text>Test Leader</Text></Row>
  <Row Tag="LOC_UNIT_TEST_NAME"><Text>Test Unit</Text></Row>
</BaseGameText>
""",
                encoding="utf-8",
            )

            profile = extract_path(root)
            self.assertEqual(profile["civilizations"][0]["attributes"]["CivilizationType"], "CIVILIZATION_TEST")
            self.assertEqual(profile["modifiers"][0]["operation"], "Update")
            self.assertEqual(profile["localized_text"]["LOC_CIV_TEST_NAME"], "Test Civ")

            prefill = profile_to_copilot_prefill(profile)
            self.assertEqual(prefill["civilization_names"], ["Test Civ"])
            self.assertEqual(prefill["leader_bindings"][0]["leader_id"], "LEADER_TEST")
            self.assertEqual(prefill["unit_names"], ["Test Unit"])


if __name__ == "__main__":
    unittest.main()
