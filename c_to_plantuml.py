""" c_to_plantuml.py
Cプロジェクト(.c/.h)から指定関数のPlantUMLシーケンス図(.puml)を生成するツール
pycparserを用いて各ファイルを解析
コメント中の [msg数字] が付与された関数呼び出しのみをメッセージ化
for -> loop, if/elseif/else -> alt/else をネストに従って展開
ライフライン名はファイル名をキーにCSVから取得。未登録なら対話的に入力してCSVへ追記
"""

import argparse
import os
import re
import csv
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Tuple, List, Optional

from pycparser import parse_file, c_ast, c_generator
import pycparser
import io
import zipfile
import urllib.request

MSG_RE = re.compile(r"\[msg([0-9]+(?:\.[0-9]+)?)\]")

# ------------------------- utilities -------------------------

def collect_source_files(src_dir: str) -> List[Path]:
    p = Path(src_dir)
    files = [f for f in p.rglob("*.c")] + [f for f in p.rglob("*.h")]
    return sorted(files)

def extract_msg_comments(src_path: Path) -> Dict[int, str]:
    mapping: Dict[int, str] = {}
    try:
        with src_path.open('r', encoding='utf-8', errors='ignore') as f:
            for i, line in enumerate(f, start=1):
                m = MSG_RE.search(line)
                if m:
                    mapping[i] = m.group(1)
    except Exception as e:
        print(f"警告: {src_path} を読み取れませんでした: {e}")
    return mapping

def cpp_preprocess(in_path: Path, fake_include_dir: Optional[str]) -> Path:
    out_fd, out_name = tempfile.mkstemp(suffix='.c')
    os.close(out_fd)
    cpp_args = ["gcc", "-E", "-C", "-P"]
    if fake_include_dir:
        cpp_args += [f"-I{fake_include_dir}"]
    cpp_args += [str(in_path), "-o", out_name]
    try:
        subprocess.run(cpp_args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode(errors='ignore') if e.stderr else ''
        raise RuntimeError(f"cpp failed for {in_path}: {stderr}")
    return Path(out_name)

# def remove_comments(text: str) -> str:
#     text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
#     text = re.sub(r'//.*', '', text)
#     return text
def remove_comments(text: str) -> str:
    def replacer(match):
        s = match.group()
        return ''.join('\n' if c == '\n' else ' ' for c in s)

    text = re.sub(r'/\*.*?\*/', replacer, text, flags=re.DOTALL)
    text = re.sub(r'//.*', '', text)
    return text
def preprocess_for_pycparser(pp_path: Path) -> Path:
    out_fd, out_name = tempfile.mkstemp(suffix='.c')
    os.close(out_fd)
    with open(pp_path, 'r', encoding='utf-8', errors='ignore') as f:
        code = f.read()
    clean = remove_comments(code)
    with open(out_name, 'w', encoding='utf-8') as f:
        f.write(clean)
    return Path(out_name)

def rewrite_coord_file(ast, orig_path: Path):
    """AST内のcoord.fileをすべて元ファイルパスに置き換える"""
    for _, node in ast.children():
        if hasattr(node, 'coord') and getattr(node.coord, 'file', None):
            node.coord.file = str(orig_path)
        rewrite_coord_file(node, orig_path)

# ------------------------- AST collectors -------------------------

class FuncDeclCollector(c_ast.NodeVisitor):
    def __init__(self, filename: str):
        self.filename = filename
        self.result: Dict[str, dict] = {}

    def _type_to_str(self, typ) -> str:
        if typ is None:
            return 'void'
        if isinstance(typ, c_ast.TypeDecl):
            inner = getattr(typ, 'type', None)
            if isinstance(inner, c_ast.IdentifierType):
                return ' '.join(inner.names)
            elif isinstance(inner, c_ast.Struct):
                return f'struct {inner.name}'
            else:
                return inner.__class__.__name__ if inner is not None else 'type'
        elif isinstance(typ, c_ast.PtrDecl):
            return self._type_to_str(typ.type) + ' *'
        elif isinstance(typ, c_ast.FuncDecl):
            return 'function'
        elif isinstance(typ, c_ast.Struct):
            return f'struct {typ.name}'
        elif isinstance(typ, c_ast.IdentifierType):
            return ' '.join(typ.names)
        else:
            return typ.__class__.__name__

    def visit_FuncDef(self, node):
        decl = node.decl
        name = getattr(decl, 'name', None)
        ftype = getattr(decl, 'type', None)
        ret_type = 'void'
        params = []
        if isinstance(ftype, c_ast.FuncDecl):
            if getattr(ftype, 'args', None) and ftype.args.params:
                for p in ftype.args.params:
                    p_name = getattr(p, 'name', None)
                    p_type = self._type_to_str(getattr(p, 'type', None))
                    params.append((p_name, p_type))
            if hasattr(ftype, 'type'):
                ret_type = self._type_to_str(ftype.type)
        if name:
            self.result[name] = {'return': ret_type, 'params': params, 'file': self.filename, 'coord': getattr(decl, 'coord', None)}
        self.generic_visit(node)

    def visit_Decl(self, node):
        if isinstance(node.type, c_ast.FuncDecl):
            name = getattr(node, 'name', None)
            ftype = node.type
            ret_type = self._type_to_str(getattr(ftype, 'type', None))
            params = []
            if getattr(ftype, 'args', None) and ftype.args.params:
                for p in ftype.args.params:
                    p_name = getattr(p, 'name', None)
                    p_type = self._type_to_str(getattr(p, 'type', None))
                    params.append((p_name, p_type))
            if name:
                self.result[name] = {'return': ret_type, 'params': params, 'file': self.filename, 'coord': getattr(node, 'coord', None)}
        self.generic_visit(node)

class StructCollector(c_ast.NodeVisitor):
    def __init__(self):
        self.structs: Dict[str, List[Tuple[str, str]]] = {}

    def _type_to_str(self, typ) -> str:
        if typ is None:
            return 'void'
        if isinstance(typ, c_ast.TypeDecl):
            inner = getattr(typ, 'type', None)
            if isinstance(inner, c_ast.IdentifierType):
                return ' '.join(inner.names)
            elif isinstance(inner, c_ast.Struct):
                return f'struct {inner.name}'
            else:
                return inner.__class__.__name__ if inner is not None else 'type'
        elif isinstance(typ, c_ast.PtrDecl):
            return self._type_to_str(typ.type) + ' *'
        elif isinstance(typ, c_ast.Struct):
            return f'struct {typ.name}'
        else:
            return typ.__class__.__name__

    def visit_Struct(self, node):
        key = node.name or '<anon>'
        if node.decls:
            members = []
            for d in node.decls:
                members.append((d.name, self._type_to_str(getattr(d, 'type', None))))
            self.structs[key] = members
        self.generic_visit(node)

# ------------------------- Sequence builder -------------------------

class SequenceBuilder:
    def __init__(self, func_node: c_ast.FuncDef, func_name: str, file_msgs: Dict[Path, Dict[int,str]], func_table: Dict[str, dict], lifemap: Dict[str,str], lifemap_csv: Path, src_file: Optional[Path] = None):
        self.func_node = func_node
        self.func_name = func_name
        self.file_msgs = file_msgs
        self.func_table = func_table
        self.lifemap = lifemap
        self.lifemap_csv = lifemap_csv
        self.lines: List[str] = []
        self.indent = 0
        self.src_file = src_file

    def emit(self, line: str):
        self.lines.append('    ' * self.indent + line)

    def build(self) -> List[str]:
        self.lines = ['@startuml']
        src_part = self.lookup_lifeline(self.src_file)
        self.lines.append(f'participant {src_part}')
        self._visit_stmt(self.func_node.body)
        self.lines.append('@enduml')
        return self.lines

    def lookup_lifeline(self, file_path: Optional[Path]) -> str:
        key = str(file_path) if file_path else 'unknown'
        if key in self.lifemap:
            return self.lifemap[key]
        suggested = f':{file_path.name}' if file_path and getattr(file_path, 'name', None) else ':unknown'
        print(f"ライフラインが見つかりません: {key}")
        try:
            val = input(f"このファイル({file_path.name if file_path else key})のライフライン名を入力してください(例 ':DeviceA') [Enterで {suggested} を利用]: ")
        except Exception:
            val = ''
        if not val or not val.strip():
            val = suggested
        self.lifemap[key] = val
        try:
            with open(self.lifemap_csv, 'a', newline='', encoding='utf-8') as csvf:
                w = csv.writer(csvf)
                w.writerow([key, val])
        except Exception as e:
            print(f"警告: lifemap を CSV に書き込めませんでした: {e}")
        return val

    # --- 修正版: call message ---
    def _call_message(self, node: c_ast.FuncCall, assign_target: Optional[str] = None) -> Optional[str]:
        coord = getattr(node, 'coord', None)
        if not coord:
            return None
        lineno = getattr(coord, 'line', None)
        if lineno is None:
            return None
        srcpath = Path(getattr(coord, 'file')) if getattr(coord, 'file', None) else None
        msgs = self.file_msgs.get(srcpath, {})
        if lineno not in msgs:
            return None
        msgid = msgs[lineno]
        if isinstance(node.name, c_ast.ID):
            callee = node.name.name
        else:
            callee = c_generator.CGenerator().visit(node.name)

        callee_info = self.func_table.get(callee)
        arg_types = []
        if getattr(node, 'args', None) and getattr(node.args, 'exprs', None):
            for idx, expr in enumerate(node.args.exprs):
                if isinstance(expr, c_ast.ID):
                    arg_name = expr.name
                else:
                    try:
                        arg_name = c_generator.CGenerator().visit(expr)
                    except Exception:
                        arg_name = '<expr>'
                if callee_info and idx < len(callee_info.get('params', [])):
                    arg_types.append(f"{arg_name}:{callee_info['params'][idx][1]}")
                else:
                    arg_types.append(f"{arg_name}:unknown")
        # void 引数は空に
        if callee_info and callee_info.get('params') == [('void',)] and not arg_types:
            args_joined = ''
        else:
            args_joined = ', '.join(arg_types)

        ret_type = callee_info.get('return') if callee_info else 'unknown'
        msg_text = f"[msg{msgid}]{callee}({args_joined}):{ret_type}"
        if assign_target:
            msg_text = f"{assign_target} = {msg_text}"
        return msg_text

    def _emit_local_msg(self, coord, text_msg):
        """Emit a local message (same lifeline -> same lifeline) if the coord line has a msg id in file_msgs."""
        if not coord:
            return False
        lineno = getattr(coord, 'line', None)
        if lineno is None:
            return False
        srcpath = Path(getattr(coord, 'file')) if getattr(coord, 'file', None) else None
        msgs = self.file_msgs.get(srcpath, {})
        if lineno not in msgs:
            return False
        msgid = msgs[lineno]
        # text_msg should be the right-hand expression or whole expr; include msg id
        src_life = self.lookup_lifeline(self.src_file)
        # ensure message includes [msgX] prefix if not present
        if '[msg' not in text_msg:
            text_msg = f"[msg{msgid}]" + text_msg
        self.emit(f"{src_life} -> {src_life} : {text_msg}")
        return True

    def _visit_stmt(self, node, parent_is_assignment_or_decl=False):
        if node is None:
            return

        if isinstance(node, c_ast.Compound):
            for stmt in node.block_items or []:
                self._visit_stmt(stmt)

        # 関数呼び出し単体（代入なし）
        elif isinstance(node, c_ast.FuncCall):
            if not parent_is_assignment_or_decl:
                msg = self._call_message(node)
                if msg:
                    callee_name = node.name.name if isinstance(node.name, c_ast.ID) else None
                    callee_info = self.func_table.get(callee_name) if callee_name else None
                    callee_file = Path(callee_info['file']) if callee_info and callee_info.get('file') else None
                    callee_life = self.lookup_lifeline(callee_file)
                    src_life = self.lookup_lifeline(self.src_file)
                    self.emit(f"{src_life} -> {callee_life} : {msg}")
            if getattr(node, 'args', None) and getattr(node.args, 'exprs', None):
                for e in node.args.exprs:
                    self._visit_stmt(e)

        
        # 代入式（関数呼び出しを含む場合と、通常代入の両方）
        elif isinstance(node, c_ast.Assignment):
            # 代入の左辺（文字列）
            try:
                left_str = c_generator.CGenerator().visit(node.lvalue)
            except Exception:
                left_str = '<lhs>'

            # 右辺が関数呼び出しの場合（既存処理）
            if isinstance(node.rvalue, c_ast.FuncCall):
                target = left_str
                msg = self._call_message(node.rvalue, assign_target=target)
                if msg:
                    callee_name = node.rvalue.name.name if isinstance(node.rvalue.name, c_ast.ID) else None
                    callee_info = self.func_table.get(callee_name) if callee_name else None
                    callee_file = Path(callee_info['file']) if callee_info and callee_info.get('file') else None
                    callee_life = self.lookup_lifeline(callee_file)
                    src_life = self.lookup_lifeline(self.src_file)
                    self.emit(f"{src_life} -> {callee_life} : {msg}")
                # visit RHS expressions for nested calls
                self._visit_stmt(node.rvalue, parent_is_assignment_or_decl=True)
            else:
                # 右辺が関数呼び出しでない通常代入 (例: a = ret; a += 3;)
                # 出力対象の行に [msgX] があるか確認してメッセージを出す
                try:
                    right_str = c_generator.CGenerator().visit(node.rvalue)
                except Exception:
                    right_str = '<expr>'
                coord = getattr(node, 'coord', None)
                # compose message text without duplicating [msgX]
                text_msg = f"{left_str} = {right_str}"
                emitted = self._emit_local_msg(coord, text_msg)
                # still traverse the rvalue to catch nested calls or unary ops inside
                self._visit_stmt(node.rvalue, parent_is_assignment_or_decl=True)
        
        # 宣言＋初期化（初期化子が関数呼び出しの場合）
        elif isinstance(node, c_ast.Decl) and getattr(node, 'init', None) and isinstance(node.init, c_ast.FuncCall):
            target = node.name
            msg = self._call_message(node.init, assign_target=target)
            if msg:
                callee_name = node.init.name.name if isinstance(node.init.name, c_ast.ID) else None
                callee_info = self.func_table.get(callee_name) if callee_name else None
                callee_file = Path(callee_info['file']) if callee_info and callee_info.get('file') else None
                callee_life = self.lookup_lifeline(callee_file)
                src_life = self.lookup_lifeline(self.src_file)
                self.emit(f"{src_life} -> {callee_life} : {msg}")
            self._visit_stmt(node.init, parent_is_assignment_or_decl=True)

        # 宣言＋初期化（初期化子が関数呼び出しでない場合：リテラルや変数代入を表現）
        elif isinstance(node, c_ast.Decl) and getattr(node, 'init', None):
            # 例: int a = 1; /*[msgX]*/ や int a = b;
            try:
                target = node.name
            except Exception:
                target = '<var>'
            coord = getattr(node, 'coord', None)
            try:
                init_str = c_generator.CGenerator().visit(node.init)
            except Exception:
                init_str = '<expr>'
            text_msg = f"{target} = {init_str}"
            self._emit_local_msg(coord, text_msg)
            # visit init to find nested calls if any
            self._visit_stmt(node.init, parent_is_assignment_or_decl=True)
        # 単項演算子（インクリメント / デクリメントなど）
        elif isinstance(node, c_ast.UnaryOp):
            # node.op examples: 'p++' (post-increment), 'p--', '++', '--', '&', '*', etc.
            # We target increments/decrements and similar mutation ops.
            try:
                op = node.op
            except Exception:
                op = None
            # get expression string for message
            try:
                expr_str = c_generator.CGenerator().visit(node)
            except Exception:
                expr_str = '<unary>'
            coord = getattr(node, 'coord', None)
            # Consider common increment/decrement op representations
            if op in ('p++', 'p--', '++', '--'):
                # emit message like "b++" if /*[msgX]*/ present on this line
                self._emit_local_msg(coord, expr_str)
            # still visit child expr
            try:
                child = getattr(node, 'expr', None)
                if child is not None:
                    self._visit_stmt(child)
            except Exception:
                pass

        # if / else
        elif isinstance(node, c_ast.If):
            cond = 'cond'
            try:
                cond = c_generator.CGenerator().visit(node.cond) if node.cond else 'cond'
            except Exception:
                cond = 'cond'
            self.emit(f"alt {cond}")
            self.indent += 1
            self._visit_stmt(node.iftrue)
            self.indent -= 1
            if node.iffalse:
                self.emit("else")
                self.indent += 1
                self._visit_stmt(node.iffalse)
                self.indent -= 1
            self.emit("end")

        # for / while ループ
        elif isinstance(node, c_ast.For):
            hdr = []
            try:
                if node.init:
                    hdr.append(c_generator.CGenerator().visit(node.init))
                if node.cond:
                    hdr.append(c_generator.CGenerator().visit(node.cond))
                if node.next:
                    hdr.append(c_generator.CGenerator().visit(node.next))
            except Exception:
                pass
            hdrs = ' '.join(hdr) if hdr else 'for'
            self.emit(f"loop {hdrs}")
            self.indent += 1
            self._visit_stmt(node.stmt)
            self.indent -= 1
            self.emit("end")
        elif isinstance(node, c_ast.While):
            cond = 'cond'
            try:
                cond = c_generator.CGenerator().visit(node.cond) if node.cond else 'cond'
            except Exception:
                cond = 'cond'
            self.emit(f"loop while {cond}")
            self.indent += 1
            self._visit_stmt(node.stmt)
            self.indent -= 1
            self.emit("end")

        # その他の宣言・return など
        elif isinstance(node, c_ast.Decl) and getattr(node, 'init', None):
            self._visit_stmt(node.init)
        elif isinstance(node, c_ast.Return):
            if node.expr:
                self._visit_stmt(node.expr)
        else:
            for _, child in node.children():
                self._visit_stmt(child)
# ------------------------- lifemap CSV -------------------------

def load_lifemap(csv_path: Path) -> Dict[str,str]:
    m: Dict[str,str] = {}
    if not csv_path.exists():
        return m
    try:
        with csv_path.open('r', encoding='utf-8') as f:
            r = csv.reader(f)
            for row in r:
                if len(row) >= 2:
                    m[row[0]] = row[1]
    except Exception as e:
        print(f"警告: lifemap CSV 読み込み失敗: {e}")
        return m
    return m

# ------------------------- main orchestration -------------------------

def ensure_fake_libc_include() -> str:
    base = os.path.dirname(pycparser.__file__)
    target = os.path.join(base, 'fake_libc_include')
    if os.path.exists(target):
        return target
    print("⚙️ fake_libc_include が見つかりません。GitHubから取得します...")
    url = "https://github.com/eliben/pycparser/archive/refs/heads/master.zip"
    with urllib.request.urlopen(url) as resp:
        z = zipfile.ZipFile(io.BytesIO(resp.read()))
        members = [m for m in z.namelist() if "fake_libc_include/" in m]
        for m in members:
            relpath = m.split("fake_libc_include/")[-1]
            if not relpath or relpath.endswith("/"):
                continue
            dest = os.path.join(target, relpath)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(z.read(m))
    print(f"✅ fake_libc_include を配置しました: {target}")
    return target

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--src', required=True, help='source root dir')
    parser.add_argument('--func', required=True, help='target function name to generate sequence for')
    parser.add_argument('--out', required=True, help='output .puml file')
    parser.add_argument('--lifemap', required=True, help='csv file mapping filepath -> ":Name"')
    args = parser.parse_args()

    src_dir = Path(args.src)
    out_path = Path(args.out)
    lifemap_csv = Path(args.lifemap)
    fake_include = ensure_fake_libc_include()
    files = collect_source_files(str(src_dir))
    print(f"解析対象ファイル数: {len(files)}")

    file_msgs: Dict[Path, Dict[int,str]] = {}
    func_table: Dict[str, dict] = {}
    struct_table: Dict[str, list] = {}
    preprocessed_map: Dict[Path, Path] = {}

    for f in files:
        try:
            pp = cpp_preprocess(f, fake_include)
            preprocessed_map[f] = pp
            file_msgs[f] = extract_msg_comments(pp)

            clean_pp = preprocess_for_pycparser(pp)
            ast = parse_file(str(clean_pp), use_cpp=False)
            rewrite_coord_file(ast, f)

            c = FuncDeclCollector(str(f))
            c.visit(ast)
            func_table.update(c.result)

            s = StructCollector()
            s.visit(ast)
            struct_table.update(s.structs)
            clean_pp.unlink(missing_ok=True)

        except Exception as e:
            print(f"警告: {f} を解析できませんでした: {e}")

    target_node = None
    target_pp = None
    for orig_f, pp in preprocessed_map.items():
        try:
            clean_pp = preprocess_for_pycparser(pp)
            ast = parse_file(str(clean_pp), use_cpp=False)
            rewrite_coord_file(ast, orig_f)
            clean_pp.unlink(missing_ok=True)
            for node in ast.ext:
                if isinstance(node, c_ast.FuncDef) and getattr(node.decl, 'name', None) == args.func:
                    target_node = node
                    target_pp = orig_f
                    break
            if target_node:
                break
        except Exception as e:
            print(f"警告2: {pp} を解析できませんでした: {e}")

    if target_node is None:
        print(f"対象関数 {args.func} が見つかりませんでした")
        return

    lifemap = load_lifemap(lifemap_csv)
    builder = SequenceBuilder(target_node, args.func, file_msgs, func_table, lifemap, lifemap_csv, src_file=target_pp)
    lines = builder.build()
    with out_path.open('w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"✅ PlantUML生成完了: {out_path}")

if __name__ == "__main__":
    main()
