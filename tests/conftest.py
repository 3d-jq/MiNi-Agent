# 让 pytest 无论从哪个目录运行,都能找到项目根目录下的模块(如 config.py)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 注意:这些测试是按「拆分后」的模块结构写的(config.py / tools_files.py / ...)。
# 如果还没做拆分,要么先按蓝图拆好,要么把各测试文件的导入临时改成 from learn import ...
