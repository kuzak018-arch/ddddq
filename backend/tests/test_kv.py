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


def test_backslash_key_binding():
    d = kv.loads('"config" { "bindings" { "\\"\t\t"toggleconsole"\n "F10" "x" } }')
    assert d["config"]["bindings"] == {"\\": "toggleconsole", "F10": "x"}


def test_escaped_quote_inside_word():
    # an escaped quote is recognised when text follows it; before whitespace "\" is the backslash key
    assert kv.loads('"a" "x\\"y"')["a"] == 'x"y'


def test_dumps_roundtrip():
    d = kv.loads(GSI_CFG)
    assert kv.loads(kv.dumps(d)) == d
