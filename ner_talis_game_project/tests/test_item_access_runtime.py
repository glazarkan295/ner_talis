import sys,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from services.item_access_runtime import grant,has_access,revoke_for_item_action

class ItemAccessRuntimeTest(unittest.TestCase):
 def test_permanent_access_item_opens_target(self):
  player={};item={"item_id":"key"};definition={"opens_access":True,"access_target":"secret_cave"}
  with patch("services.item_access_runtime.definition",return_value=definition):result=grant(player,item)
  self.assertEqual(result["target"],"secret_cave");self.assertTrue(has_access(player,"secret_cave"))
 def test_temporary_access_has_expiration(self):
  player={};item={"item_id":"pass"};definition={"opens_access":True,"access_target":"event_shop","access_temporary":True,"access_duration":60}
  with patch("services.item_access_runtime.definition",return_value=definition):grant(player,item)
  self.assertIn("expires_at",player["unlocks"]["event_shop"]);self.assertTrue(has_access(player,"event_shop"))
 def test_typed_inventory_equipped_and_action_lifetime(self):
  player={"inventory":[{"item_id":"key","amount":1}],"equipment":[]};item={"item_id":"key"};definition={"opens_access":True,"access_type":"location","access_target_id":"cave","access_while_inventory":True,"access_lose_on_transfer":True}
  with patch("services.item_access_runtime.definition",return_value=definition):grant(player,item)
  self.assertTrue(has_access(player,"cave"));self.assertTrue(has_access(player,"location:cave"))
  player["inventory"]=[];self.assertFalse(has_access(player,"cave"))
  player["inventory"]=[item];self.assertGreaterEqual(revoke_for_item_action(player,"key","transfer"),1);self.assertFalse(has_access(player,"cave"))

if __name__=="__main__":unittest.main()
