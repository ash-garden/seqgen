""" c_to_plantuml.py

Cプロジェクト(.c/.h)から指定関数のPlantUMLシーケンス図(.puml)を生成するツール

pycparserを用いて各ファイルを解析

コメント中の [msg数字] が付与された関数呼び出しのみをメッセージ化

for -> loop, if/elseif/else -> alt/else をネストに従って展開

ライフライン名はファイル名をキーにCSVから取得。未登録なら対話的に入力してCSVへ追記


使い方例: python c_to_plantuml.py --src ./src --func target_function --out output.puml --lifemap lifelines.csv

依存: pip install pycparser gcc (プリプロセッサを利用するため)

注意:

完全な型解決（外部ライブラリやマクロに依存する型）は本スクリプトでは最小限の解決のみ行います。

プリプロセスはファイル単位で行い、コメントは別に生ファイルから抽出して行番号を保持します。

メッセージIDは小数も可（例: [msg1.2]）


"""

import argparse import os import re import csv import subprocess import tempfile from pathlib import Path from typing import Dict, Tuple, List, Optional

from pycparser import parse_file, c_ast, c_parser, c_generator import pycparser

MSG_RE = re.compile(r"")

------------------------- utilities -------------------------

def collect_source_files(src_dir: str) -> List[Path]: p = Path(src_dir) files = [f for f in p.rglob(".c")] + [f for f in p.rglob(".h")] return sorted(files)

def extract_msg_comments(src_path: Path) -> Dict[int, str]: """ソースを行単位で読み、各行にある [msgN] を抽出して {lineno: msgid} を返す""" mapping = {} with src_path.open('r', encoding='utf-8', errors='ignore') as f: for i, line in enumerate(f, start=1): m = MSG_RE.search(line) if m: mapping[i] = m.group(1)  # '1' or '1.2' etc. return mapping

def cpp_preprocess(in_path: Path, fake_include_dir: Optional[str]) -> Path: """gccでプリプロセスして一時ファイルを返す（-P を使い #line を出させない）""" out_fd, out_name = tempfile.mkstemp(suffix='.c') os.close(out_fd) cpp_args = ["gcc", "-E", "-P", str(in_path), "-o", out_name] if fake_include_dir: cpp_args[3:3] = [f"-I{fake_include_dir}"]  # insert after -E -P try: subprocess.run(cpp_args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE) except subprocess.CalledProcessError as e: raise RuntimeError(f"cpp failed for {in_path}: {e.stderr.decode()}") return Path(out_name)

------------------------- AST collectors -------------------------

class FuncDeclCollector(c_ast.NodeVisitor): """プロジェクト中の関数宣言/定義を集める result: name -> dict(return_type, params: [(name,type)], file, coord) """ def init(self, filename: str): self.filename = filename self.result = {}

def _type_to_str(self, typ) -> str:
    # 対応できる範囲で型文字列にする
    if isinstance(typ, c_ast.TypeDecl):
        if isinstance(typ.type, c_ast.IdentifierType):
            return ' '.join(typ.type.names)
        else:
            return typ.type.__class__.__name__
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
    name = decl.name
    ftype = decl.type
    ret_type = 'void'
    params = []
    if isinstance(ftype, c_ast.FuncDecl):
        if ftype.args:
            for p in ftype.args.params:
                p_name = getattr(p, 'name', None)
                p_type = self._type_to_str(p.type)
                params.append((p_name, p_type))
        if hasattr(ftype, 'type'):
            ret_type = self._type_to_str(ftype.type)
    self.result[name] = {'return': ret_type, 'params': params, 'file': self.filename, 'coord': getattr(decl, 'coord', None)}
    self.generic_visit(node)

def visit_Decl(self, node):
    # 関数プロトタイプ（宣言）
    if isinstance(node.type, c_ast.FuncDecl):
        name = node.name
        ftype = node.type
        ret_type = self._type_to_str(ftype.type) if hasattr(ftype, 'type') else 'void'
        params = []
        if ftype.args:
            for p in ftype.args.params:
                p_name = getattr(p, 'name', None)
                p_type = self._type_to_str(p.type)
                params.append((p_name, p_type))
        self.result[name] = {'return': ret_type, 'params': params, 'file': self.filename, 'coord': getattr(node, 'coord', None)}
    self.generic_visit(node)

class StructCollector(c_ast.NodeVisitor): def init(self): self.structs = {}  # name -> [(member_name, type_str)]

def _type_to_str(self, typ) -> str:
    if isinstance(typ, c_ast.TypeDecl):
        if isinstance(typ.type, c_ast.IdentifierType):
            return ' '.join(typ.type.names)
        elif isinstance(typ.type, c_ast.Struct):
            return f'struct {typ.type.name}'
        else:
            return typ.type.__class__.__name__
    elif isinstance(typ, c_ast.PtrDecl):
        return self._type_to_str(typ.type) + ' *'
    elif isinstance(typ, c_ast.Struct):
        return f'struct {typ.name}'
    else:
        return typ.__class__.__name__

def visit_Struct(self, node):
    if node.decls:
        members = []
        for d in node.decls:
            members.append((d.name, self._type_to_str(d.type)))
        self.structs[node.name] = members
    self.generic_visit(node)

------------------------- Sequence builder -------------------------

class SequenceBuilder: def init(self, func_node: c_ast.FuncDef, func_name: str, file_msgs: Dict[Path, Dict[int,str]], func_table: Dict[str, dict], lifemap: Dict[str,str], lifemap_csv: Path): self.func_node = func_node self.func_name = func_name self.file_msgs = file_msgs  # Path-> {lineno: msgid} self.func_table = func_table self.lifemap = lifemap  # filename -> ":Name" self.lifemap_csv = lifemap_csv self.lines: List[str] = [] self.indent = 0 self.src_file = Path(getattr(func_node.decl, 'coord').file) if getattr(func_node.decl, 'coord', None) else None

def emit(self, line: str):
    self.lines.append('    ' * self.indent + line)

def build(self) -> List[str]:
    # header
    self.lines = ['@startuml']
    # participants: ensure source function lifeline present
    src_part = self.lookup_lifeline(self.src_file)
    self.lines.append(f'participant {src_part}')
    # traverse body
    self._visit_stmt(self.func_node.body)
    self.lines.append('@enduml')
    return self.lines

def lookup_lifeline(self, file_path: Optional[Path]) -> str:
    key = str(file_path) if file_path else 'unknown'
    if key in self.lifemap:
        return self.lifemap[key]
    # ask user
    suggested = f':{file_path.name}' if file_path else ':unknown'
    print(f"ライフラインが見つかりません: {key}")
    val = input(f"このファイル({file_path.name if file_path else key})のライフライン名を入力してください(例 ':DeviceA') [Enterで {suggested} を利用]: ")
    if not val.strip():
        val = suggested
    # store into csv
    self.lifemap[key] = val
    try:
        with open(self.lifemap_csv, 'a', newline='', encoding='utf-8') as csvf:
            w = csv.writer(csvf)
            w.writerow([key, val])
    except Exception as e:
        print(f"警告: lifemap を CSV に書き込めませんでした: {e}")
    return val

def _call_message(self, node: c_ast.FuncCall) -> Optional[str]:
    # find lineno
    coord = getattr(node, 'coord', None)
    if not coord:
        return None
    lineno = coord.line
    # find msg in the file's mapping
    srcpath = Path(coord.file)
    msgs = self.file_msgs.get(srcpath, {})
    if lineno not in msgs:
        return None
    msgid = msgs[lineno]
    # callee name
    if isinstance(node.name, c_ast.ID):
        callee = node.name.name
    else:
        callee = c_generator.CGenerator().visit(node.name)
    # args: best-effort list of arg expressions names
    arg_strs = []
    if node.args and getattr(node.args, 'exprs', None):
        for expr in node.args.exprs:
            # try to get simple representation
            if isinstance(expr, c_ast.ID):
                arg_name = expr.name
            else:
                arg_name = c_generator.CGenerator().visit(expr)
            arg_strs.append(arg_name)
    # try to get types from func_table
    callee_info = self.func_table.get(callee)
    arg_types = []
    if callee_info:
        for idx, (pname, ptype) in enumerate(callee_info.get('params', [])):
            # if arg exists at same index, pair them
            if idx < len(arg_strs):
                arg_types.append(f"{arg_strs[idx]}:{ptype}")
            else:
                arg_types.append(f"{pname or 'arg'+str(idx)}:{ptype}")
    else:
        # unknown function: show arg names only
        for a in arg_strs:
            arg_types.append(f"{a}:unknown")
    ret_type = callee_info.get('return') if callee_info else 'unknown'
    # format per requirement: [msg数字]呼出している関数名(関数の引数:関数の引数の型):呼出している関数の型
    args_joined = ', '.join(arg_types)
    msg_text = f"[msg{msgid}]{callee}({args_joined}):{ret_type}"
    return msg_text

def _visit_stmt(self, node):
    # handle compound statements
    if node is None:
        return
    nodetype = type(node)
    if isinstance(node, c_ast.Compound):
        for stmt in node.block_items or []:
            self._visit_stmt(stmt)
    elif isinstance(node, c_ast.FuncCall):
        msg = self._call_message(node)
        if msg:
            # determine callee file to get lifeline
            callee_name = node.name.name if isinstance(node.name, c_ast.ID) else c_generator.CGenerator().visit(node.name)
            callee_info = self.func_table.get(callee_name)
            callee_file = Path(callee_info['file']) if callee_info and callee_info.get('file') else None
            callee_life = self.lookup_lifeline(callee_file)
            src_life = self.lookup_lifeline(self.src_file)
            self.emit(f"{src_life} -> {callee_life} : {msg}")
        # still visit args if any
        if getattr(node, 'args', None):
            for e in getattr(node.args, 'exprs', []) or []:
                self._visit_stmt(e)
    elif isinstance(node, c_ast.If):
        # PlantUML alt block
        # visit condition in a comment? we'll emit alt with condition text
        cond = c_generator.CGenerator().visit(node.cond) if node.cond else 'cond'
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
    elif isinstance(node, c_ast.For):
        # simple loop block
        # try to get loop header
        hdr = []
        if node.init:
            hdr.append(c_generator.CGenerator().visit(node.init))
        if node.cond:
            hdr.append(c_generator.CGenerator().visit(node.cond))
        if node.next:
            hdr.append(c_generator.CGenerator().visit(node.next))
        hdrs = ' '.join(hdr) if hdr else 'for'
        self.emit(f"loop {hdrs}")
        self.indent += 1
        self._visit_stmt(node.stmt)
        self.indent -= 1
        self.emit("end")
    elif isinstance(node, c_ast.While):
        cond = c_generator.CGenerator().visit(node.cond) if node.cond else 'cond'
        self.emit(f"loop while {cond}")
        self.indent += 1
        self._visit_stmt(node.stmt)
        self.indent -= 1
        self.emit("end")
    elif isinstance(node, c_ast.Decl) and getattr(node, 'init', None):
        # initializers may contain function calls; descend
        self._visit_stmt(node.init)
    elif isinstance(node, c_ast.Return):
        if node.expr:
            self._visit_stmt(node.expr)
    else:
        # generic descent for other node types
        for _, child in node.children():
            self._visit_stmt(child)

------------------------- lifemap CSV -------------------------

def load_lifemap(csv_path: Path) -> Dict[str,str]: m = {} if not csv_path.exists(): return m try: with csv_path.open('r', encoding='utf-8') as f: r = csv.reader(f) for row in r: if len(row) >= 2: m[row[0]] = row[1] except Exception as e: print(f"警告: lifemap CSV 読み込み失敗: {e}") return m

------------------------- main orchestration -------------------------

def main(): parser = argparse.ArgumentParser() parser.add_argument('--src', required=True, help='source root dir') parser.add_argument('--func', required=True, help='target function name to generate sequence for') parser.add_argument('--out', required=True, help='output .puml file') parser.add_argument('--lifemap', required=True, help='csv file mapping filepath -> ":Name"') args = parser.parse_args()

src_dir = Path(args.src)
out_path = Path(args.out)
lifemap_csv = Path(args.lifemap)

fake_include = os.path.join(os.path.dirname(pycparser.__file__), 'utils', 'fake_libc_include')

files = collect_source_files(str(src_dir))
print(f"解析対象ファイル数: {len(files)}")

# step1: extract comments from raw files
file_msgs: Dict[Path, Dict[int,str]] = {}
for f in files:
    file_msgs[f] = extract_msg_comments(f)

# step2: preprocess & parse each file to collect functions and structs
func_table = {}
struct_table = {}

for f in files:
    try:
        pp = cpp_preprocess(f, fake_include)
        ast = parse_file(str(pp), use_cpp=False)  # already preprocessed
        # collect functions
        c = FuncDeclCollector(str(f))
        c.visit(ast)
        func_table.update(c.result)
        # collect structs
        s = StructCollector()
        s.visit(ast)
        struct_table.update(s.structs)
    except Exception as e:
        print(f"警告: {f} を解析できませんでした: {e}")

# find target function definition
target_node = None
target_file = None
# We'll reparse files with cpp but search for FuncDef nodes matching name
for f in files:
    try:
        pp = cpp_preprocess(f, fake_include)
        ast = parse_file(str(pp), use_cpp=False)
        # find function def
        for node in ast.ext:
            if isinstance(node, c_ast.FuncDef) and node.decl.name == args.func:
                target_node = node
                target_file = f
                break
        if target_node:
            break
    except Exception as e:
        continue

if not target_node:
    print(f"エラー: 関数 {args.func} の定義が見つかりませんでした。")
    return

lifemap = load_lifemap(lifemap_csv)

builder = SequenceBuilder(target_node, args.func, file_msgs, func_table, lifemap, lifemap_csv)
uml_lines = builder.build()

out_path.parent.mkdir(parents=True, exist_ok=True)
with out_path.open('w', encoding='utf-8') as f:
    f.write('\n'.join(uml_lines))

print(f"出力完了: {out_path}")

if name == 'main': main()
