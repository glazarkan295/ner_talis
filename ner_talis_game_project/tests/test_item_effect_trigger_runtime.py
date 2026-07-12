import random,sys,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from services.item_effect_trigger_runtime import trigger,trigger_owned

class ItemEffectTriggerRuntimeTest(unittest.TestCase):
 def test_only_matching_trigger_applies_and_link_overrides_payload(self):
  item={"item_id":"ring"};data={"effect_links":[{"effect_id":"might","trigger":"on_equip","chance":100,"duration_turns":3,"strength":7},{"effect_id":"skip","trigger":"on_use"}]};player={}
  with patch("services.item_effect_trigger_runtime.definition",return_value=data),patch("services.item_effect_trigger_runtime.apply_to_player",return_value={"effect_id":"might"}) as apply:
   rows=trigger(player,item,"on_equip",rng=random.Random(1))
  self.assertEqual(rows,[{"effect_id":"might","duration_turns":3,"value":7.0}]);apply.assert_called_once()
 def test_owned_dispatches_inventory_and_equipment(self):
  player={"inventory":[{"item_id":"a"}],"equipment":{"ring":{"item_id":"b"}}}
  with patch("services.item_effect_trigger_runtime.trigger",return_value=[{"ok":1}]) as invoke:rows=trigger_owned(player,"on_craft")
  self.assertEqual(len(rows),2);self.assertEqual(invoke.call_count,2)

if __name__=="__main__":unittest.main()
