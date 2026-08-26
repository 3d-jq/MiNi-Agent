"""文件类工具测试:read/grep/write/edit/glob/list_dir —— 全部本地运行,无网络、无 API 依赖。"""
import tools_files as tf


def test_write_then_read_roundtrip(tmp_path):
    p = tmp_path / "a.txt"
    assert "已写入" in tf.write(str(p), "你好\nworld")
    assert tf.read(str(p)) == "你好\nworld"


def test_read_with_offset_and_limit(tmp_path):
    p = tmp_path / "lines.txt"
    tf.write(str(p), "\n".join(f"L{i}" for i in range(1, 11)))
    part = tf.read(str(p), start_line=3, max_lines=2)
    assert part.splitlines() == ["L3", "L4"]


def test_read_missing_file(tmp_path):
    assert "不存在" in tf.read(str(tmp_path / "nope.txt"))


def test_read_wrong_encoding_gives_hint(tmp_path):
    p = tmp_path / "gbk.txt"
    p.write_bytes("中文内容".encode("gbk"))
    result = tf.read(str(p), encoding="utf-8")
    assert "编码" in result  # 提示换编码而不是裸抛异常


def test_write_creates_parent_dirs(tmp_path):
    deep = tmp_path / "x" / "y" / "z.txt"
    tf.write(str(deep), "data")
    assert deep.read_text(encoding="utf-8") == "data"


def test_grep_finds_lines(tmp_path):
    p = tmp_path / "code.txt"
    tf.write(str(p), "alpha = 1\nbeta = alpha + 1\ngamma = 3")
    result = tf.grep(str(p), "alpha")
    assert "行 1" in result and "行 2" in result and "gamma" not in result


def test_grep_no_match_message(tmp_path):
    p = tmp_path / "empty.txt"
    tf.write(str(p), "hello")
    assert "没找到匹配" in tf.grep(str(p), "不存在的词")


def test_edit_replaces_unique_match(tmp_path):
    p = tmp_path / "e.txt"
    tf.write(str(p), "foo bar baz")
    assert "已替换" in tf.edit(str(p), "bar", "qux")
    assert tf.read(str(p)) == "foo qux baz"


def test_edit_refuses_ambiguous_match(tmp_path):
    p = tmp_path / "dup.txt"
    tf.write(str(p), "same same same")
    before = tf.read(str(p))
    assert "2 处匹配" in tf.edit(str(p), "same", "X") or "3 处匹配" in tf.edit(str(p), "same", "X")
    assert tf.read(str(p)) == before  # 拒绝时文件必须原样


def test_edit_dry_run_changes_nothing(tmp_path):
    p = tmp_path / "d.txt"
    tf.write(str(p), "abc")
    tf.edit(str(p), "a", "X", dry_run=True)
    assert tf.read(str(p)) == "abc"


def test_glob_finds_py_files_recursive(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "main.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "util.py").write_text("", encoding="utf-8")
    (tmp_path / "notes.md").write_text("", encoding="utf-8")
    result = tf.glob("**/*.py", base_dir=str(tmp_path))
    assert "main.py" in result and "util.py" in result and "notes.md" not in result


def test_glob_missing_dir_message(tmp_path):
    assert "目录不存在" in tf.glob("*", base_dir=str(tmp_path / "ghost"))


def test_list_dir_shows_entries(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "file.txt").write_text("", encoding="utf-8")
    result = tf.list_dir(str(tmp_path))
    assert "sub" in result and "file.txt" in result


def test_list_dir_empty(tmp_path):
    assert "空目录" in tf.list_dir(str(tmp_path))
