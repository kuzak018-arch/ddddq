from drafter import kv

GSI_CFG = '''"Dota Draft Helper"
{
	"uri"		"http://127.0.0.1:47821/gsi"   // comment
	"data"
	{
		"provider"	"1"
		"map"		"1"
	}
	"empty"	""
}
'''


def test_loads_nested_and_comments():
    d = kv.loads(GSI_CFG)["Dota Draft Helper"]
    assert d["uri"] == "http://127.0.0.1:47821/gsi"
    assert d["data"] == {"provider": "1", "map": "1"}
    assert d["empty"] == ""


def test_windows_paths_with_escaped_backslashes():
    d = kv.loads('"libraryfolders" { "1" { "path" "D:\\\\SteamLibrary" } }')
    assert d["libraryfolders"]["1"]["path"] == "D:\\SteamLibrary"


def test_dumps_roundtrip():
    d = kv.loads(GSI_CFG)
    assert kv.loads(kv.dumps(d)) == d
