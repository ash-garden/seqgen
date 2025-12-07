// importPackage(javax.swing);
// importPackage(java.io);

var newDiagramName = 'New Class Diagram';
 
run();
 
function run() {
    if (!isSupportedAstah()) {
        print('This edition is not supported');
    }
 
    // with (new JavaImporter(com.change_vision.jude.api.inf.editor)) {
    //     // Edit the astah model
    //     TransactionManager.beginTransaction();
    //     var editor = astah.getDiagramEditorFactory().getClassDiagramEditor();
    //     var newDgm = editor.createClassDiagram(astah.getProject(), newDiagramName);
    //     TransactionManager.endTransaction();
    //     print('New Class Diagram was created!');
    // }
    
    var file = showOpenFileDialog(); //https://docs.oracle.com/javase/jp/8/docs/api/java/io/File.html
    if(file==null)
    {
        print("終了");
        return;
    }
    // printFileLines(file);
    print("ファイル名"+file.getName());
    var seqName = createSeqName(file.getName());
    var newDgm = getNewSeqDiagram(seqName)
    
    // Open the diagram
    var dgmViewManager = astah.getViewManager().getDiagramViewManager();
    dgmViewManager.open(newDgm);

    var ll = createLifelines(file);
    var maxX = getXEndLifeLine(ll);
    var HashMap = Java.type("java.util.LinkedHashMap");
    var LastSource = new HashMap(ll);
    var outPutY = 0;
    with (new JavaImporter(com.change_vision.jude.api.inf.editor)) {
        // Edit the astah model
        TransactionManager.beginTransaction();
        var editor = astah.getDiagramEditorFactory().getSequenceDiagramEditor();

        createSequence(file,editor,LastSource,ll,outPutY);
        // createMessage("get","main","main","msg1","a,b,c","ret","int",editor, LastSource,100);
        // createMessage("get","main","aaa","msg1","a,b,c","ret","int",editor, LastSource,200);
        // createMessage("get","main","aaa","msg1","a,b,c","ret","int",editor, LastSource,300);

        // // temp = editor.createMessage("get",ll.get("main"),ll.get("aaa"),100);
        // // var mdl = temp.getModel();
        // // mdl.setGuard("msg1");
        // // mdl.setReturnValueVariable("ret");
        // // mdl.setArgument("a,b,c")
        // // temp = editor.createMessage("get",temp.getSource(),ll.get("aaa"),200);
        // line = createMessage("get","main","aaa","msg2","a,b,c","ret",editor, LastSource,line);

        // // point = new Point2D(50,300);
        // point = temp.getPoints();
        // print(point);
        // print(point[0]);
        // var Point2D = Java.type("java.awt.geom.Point2D");
        // // temp2 = editor.createCombinedFragment("", "loop", new Point2D.Double(50, 300), maxX + 200, 200);
        // // var mdl = temp2.getModel();
        // // print("isloop"+mdl.isLoop());

        // // var operands = mdl.getOperands();
        // // print(mdl.getClass());
        // // var op = operands[0];
        // // op.setGuard("i=0;i<100;i++");
        // temp2 = editor.createCombinedFragment("", "alt", new Point2D.Double(50, 300), maxX + 200, 200);
        // var mdl = temp2.getModel();
        // print("isloop"+mdl.isLoop());
        // // var ops = mdl.getInteractionOperands()
        // // mdl.setGuard("aaa")
        // var ops = mdl.getInteractionOperands()
        // var op = ops[0];
        // op.setGuard("bbb"); //https://members.change-vision.com/javadoc/astah-api/10_1_0/api/ja/doc/javadoc/com/change_vision/jude/api/inf/model/ICombinedFragment.html

        // // mdl.addInteractionOperand("","aaa")

        // temp = editor.createMessage("get",temp.getSource(),ll.get("aaa"),400);
        // // mdl.addInteractionOperand("","aaa") //https://members.change-vision.com/javadoc/astah-api/10_1_0/api/ja/doc/javadoc/com/change_vision/jude/api/inf/model/ICombinedFragment.html

        // temp2.setHeight(300);


        // temp = editor.createMessage("get",temp.getSource(),ll.get("aaa"),500);

        // temp = editor.createMessage("get",temp.getSource(),ll.get("aaa"),600);
        // // temp = editor.createCombinedFragment("loop","loop",point[0],100,100);
        // // editor.createMessage("get","main","aaa",200);
        TransactionManager.endTransaction();
    }
    
}

var EventType = Object.freeze({
    MESSAGE: "MESSAGE",
    ALT: "ALT",
    LOOP: "LOOP",
    ELSE: "ELSE",
    END: "END",
    OTHER: "OTHER"
});

EVENT_MESSAGE = 1
EVENT_ALT     = 2
EVENT_LOOP    = 3
EVENT_ELSE    = 4
EVENT_END     = 5
var  EVENT_OTHER   = 6

function createSequence(file,editor,LastSource,ll,outPutY)
{
    var FileReader  = Java.type("java.io.FileReader");
    var BufferedReader = Java.type("java.io.BufferedReader");
    var lineno = 0;
    var nestOffsetX = 0;
    var br = new BufferedReader(new FileReader(file));
    try {
        var line;
        while ((line = br.readLine()) != null) {
            lineno +=1;
            print("-")
            var kind = detectEventType(line)
            print("kind:"+kind)
            switch (kind) {
                case "EVENT_MESSAGE":
                    print("MESSAGE: " + line);
                    outPutY +=100;
                    createMessageProcess(line,editor, LastSource, ll, outPutY);
                    // msgInfo = parseMessageLine(line);
                    // print(msgInfo.funcName);
                    // createMessage(msgInfo.funcName, msgInfo.from, msgInfo.to, msgInfo.guard, msgInfo.args, msgInfo.assignVar, msgInfo.returnType, editor, LastSource, outPutY)
                    break;
                case "EVENT_ALT":
                    print("ALT: " + line);
                    outPutY +=100;
                    lineno = altProcess(line,nestOffsetX,br,lineno,file, editor, LastSource, ll, outPutY)
                    break;
                case "EVENT_LOOP":
                    print("LOOP: " + line);
                    outPutY +=100;
                    lineno = loopProcess(line,nestOffsetX,br,lineno,file, editor, LastSource, ll, outPutY)
                    break;
                case "EVENT_ELSE":
                    print("ELSE: " + line);
                    break;
                case "EVENT_END":
                    print("END: " + line);
                    break;
                default:
                    print("OTHER: " + line);
                    break;
            }            
        }
    } finally {
        br.close();
    }
}

function loopProcess(line,nestOffsetX, br,lineno,file, editor, LastSource, ll, outPutY)
{
    var mdl = createLoopProcess(line,nestOffsetX,br,lineno,file,editor,LastSource, ll, outPutY)
    while ((line = br.readLine()) != null) {
        lineno +=1;
        print("loopProcess loop top")
        var kind = detectEventType(line)
        print("kind:"+kind)
        switch (kind) {
            case "EVENT_MESSAGE":
                print("LOOP/MESSAGE: " + line);
                outPutY +=100;
                createMessageProcess(line,editor, LastSource, ll, outPutY);
                break;
            case "EVENT_ALT":
                print("LOOP/ALT: " + line);
                outPutY +=100;
                lineno = altProcess(line,nestOffsetX+10,br,lineno,file, editor, LastSource, ll, outPutY)
                break;
            case "EVENT_LOOP":
                print("LOOP/LOOP: " + line);
                outPutY +=100;
                lineno = loopProcess(line,nestOffsetX+10,br,lineno,file, editor, LastSource, ll, outPutY)
                break;
            case "EVENT_ELSE":
                print("LOOP/ELSE: " + line);
                break;
            case "EVENT_END":
                outPutY +=100;
                print("LOOP/END: " + line);
                return lineno;
                break;
            default:
                print("LOOP/OTHER: " + line);
                break;
        }            
    }
    print("exit loopProcess")
    return lineno;
}



function altProcess(line,nestOffsetX, br,lineno,file, editor, LastSource, ll, outPutY)
{
    var mdl = createAltProcess(line,nestOffsetX,br,lineno,file,editor,LastSource, ll, outPutY)
    while ((line = br.readLine()) != null) {
        lineno +=1;
        var kind = detectEventType(line)
        print("kind"+kind)
        switch (kind) {
            case "EVENT_MESSAGE":
                print("LOOP/MESSAGE: " + line);
                outPutY +=100;
                createMessageProcess(line,editor, LastSource, ll, outPutY);
                break;
            case "EVENT_ALT":
                print("LOOP/ALT: " + line);
                outPutY +=100;
                lineno = altProcess(line,nestOffsetX+10,br,lineno,file, editor, LastSource, ll, outPutY)
                break;
            case "EVENT_LOOP":
                print("LOOP/LOOP: " + line);
                outPutY +=100;
                lineno = loopProcess(line,nestOffsetX+10,br,lineno,file, editor, LastSource, ll, outPutY)
                break;
            case "EVENT_ELSE":
                print("LOOP/ELSE: " + line);
                outPutY +=100;
                createElseProcess(line,nestOffsetX,br,lineno,file,editor,LastSource, ll, outPutY,mdl)
                break;
            case "EVENT_END":
                print("LOOP/END: " + line);
                return lineno;
                break;
            default:
                print("LOOP/OTHER: " + line);
                break;
        }            
    }
    return lineno;
}



function createLoopProcess(line,nestOffsetX,br,lineno,file,editor,LastSource, ll, outPutY)
{
    print("createLoopProcess")
    var x = nestOffsetX + 20
    var y = outPutY
    var w = getXEndLifeLine(ll) +200 - x - nestOffsetX
    countSubEvent = countEventsInBlock(file,lineno);
    print("countSubEvent="+countSubEvent.count)
    var h = (countSubEvent.count-1) * 100 + 100
    var gard = getLoopCondition(line)
    print("gard="+gard);

    var mdl = createLoop(gard, x, y, w, h, editor,LastSource,ll,outPutY)
    return mdl
}   
function createAltProcess(line,nestOffsetX,br,lineno,file,editor,LastSource, ll, outPutY)
{
    var x = nestOffsetX + 20
    var y = outPutY
    var w = getXEndLifeLine(ll) +200- x - nestOffsetX
    countSubEvent = countEventsInBlock(file,lineno);
    print("countSubEvent="+countSubEvent.count)
    var h = (countSubEvent.count-1) * 100 + 100
    var gard = getAltCondition(line)

    var mdl = createAlt(gard, x, y, w, h, editor,LastSource,ll,outPutY)
    return mdl
}

function createElseProcess(line,nestOffsetX,br,lineno,file,editor,LastSource, ll, outPutY,mdl)
{
    mdl.addInteractionOperand("","else")
}

function getLoopCondition(line) {
    if (!line) return "";

    // 両端の空白を除去
    var s = line.trim();

    // 行頭が loop でなければ無効
    if (!/^loop\b/.test(s)) {
        return "";
    }

    // "loop" の後ろの文字列を取得
    var m = s.match(/^loop\s+(.*)$/);

    if (m && m[1]) {
        return m[1].trim();
    }

    return "";
}


function getAltCondition(line) {
    if (!line) return "";

    // 両端の空白を除去
    var s = line.trim();

    // 行頭が alt でなければ無効
    if (!/^alt\b/.test(s)) {
        return "";
    }

    // "alt" の後ろの文字列を取得
    var m = s.match(/^alt\s+(.*)$/);

    if (m && m[1]) {
        return m[1].trim();
    }

    return "";
}

function countEventsInBlock(filePath, startLineNum) {

    var FileReader  = Java.type("java.io.FileReader");
    var BufferedReader = Java.type("java.io.BufferedReader");
    var br = new BufferedReader(new FileReader(filePath));

    // var fr = new FileReader(filePath);
    // var br = new BufferedReader(fr);

    var line;
    var currentLine = 0;
    var blockDepth = 0;
    var count = 0;

    // startLineNum まで読み捨て
    while (currentLine < startLineNum && (line = br.readLine()) != null) {
        currentLine++;
    }

    // startLine 自体を解析
    var startType = detectEventType(line);

    if (startType !== "EVENT_LOOP" && startType !== "EVENT_ALT") {
        print("ERROR: startLine is not LOOP or ALT");
        br.close();
        return { count: 0, endLine: startLineNum };
    }

    // 最初のブロック → 深さ1
    blockDepth = 1;

    // 1行下から読み始め
    while ((line = br.readLine()) != null) {
        currentLine++;

        var t = detectEventType(line);

        // 対象イベントはすべてカウント
        if (t !== "EVENT_OTHER") {
            count++;
        }

        // ネスト処理
        if (t === "EVENT_LOOP" || t === "EVENT_ALT") {
            blockDepth++;
        } else if (t === "EVENT_END") {
            blockDepth--;
            if (blockDepth === 0) {
                // ブロック終了
                br.close();
                return { count: count, endLine: currentLine };
            }
        }
    }

    br.close();
    return { count: count, endLine: currentLine };
}

function detectEventType(line) {
    print("detectEventType (line=):"+line)
    if (!line) return EVENT_OTHER;
    var s = line.trim();
    // MESSAGE: A -> B : ...
    if (/^[A-Za-z0-9_]+\s*->\s*[A-Za-z0-9_]+\s*:/.test(s)) {
        return "EVENT_MESSAGE";
    }

    // ALT: "alt 条件"
    if (/^alt\b/.test(s)) {
        return "EVENT_ALT";
    }

    // ELSE: "else"
    if (/^else\b/.test(s)) {
        return "EVENT_ELSE";
    }

    // LOOP: "loop 条件"
    if (/^loop\b/.test(s)) {
        print("1")
        return "EVENT_LOOP";
    }

    // END: "end"
    if (/^end\b/.test(s)) {
        return "EVENT_END";
    }

    return "EVENT_OTHER";
}

// function MessageProcess(line, editor, LastSource, outPutY) {


//     print("MessageProcess start")

//     // ---------------------------------------------
//     // from → to の抽出
//     // ---------------------------------------------
//     var ft = line.match(/(\w+)\s*->\s*(\w+)\s*:/);
//     if (!ft) return null;
//     from = ft[1];
//     to = ft[2];
//     print("MessageProcess s2")

//     // ---------------------------------------------
//     // コロン以降（右辺）を取得
//     // ---------------------------------------------
//     var afterColon = line.split(":")[1].trim();

//     print("MessageProcess 3")
//     // ---------------------------------------------
//     // 戻り値格納変数の抽出（例：ret = ...）
//     // ---------------------------------------------
//     var assignMatch = afterColon.match(/^(\w+)\s*=\s*(.*)$/);
//     if (assignMatch) {
//         assignVar = assignMatch[1];
//         afterColon = assignMatch[2].trim();
//     }
//     else{
//         assignVar = ""
//     }
//     print("MessageProcess 4")

//     // ---------------------------------------------
//     // メッセージ ID 抽出 [msg1.1]
//     // ---------------------------------------------
//     var msgIdMatch = afterColon.match(/^\[(msg[^\]]+)\]/);
//     if (msgIdMatch) {
//         guard = msgIdMatch[1];
//         afterColon = afterColon.replace(/^\[(msg[^\]]+)\]/, "").trim();
//     }
//     print("MessageProcess 5")

//     // ---------------------------------------------
//     // 関数名 + 引数 + 戻り値型
//     //   sub_func(&a:int *, 2:char, &st:SUBFUNCSTRUCT *):int
//     // ---------------------------------------------
//     // var funcMatch = afterColon.match(/^(\w+)\s*\((.*)\)\s*:(\w+)\s*$/);
//     print("afterColon="+afterColon)
//     var funcMatch = afterColon.match(/^(\w+)\s*\((.*?)\)\s*:(\w+)\s*$/);
//     if (!funcMatch){
//         print("!func")
//         funcName = ""
//         args = ""
//         returnType = ""
//     }else{
//         funcName = funcMatch[1];
//         var argsStr = funcMatch[2];
//         returnType = funcMatch[3];
//         print("MessageProcess 6")
//         // ---------------------------------------------
//         // 引数を配列に分解
//         // ---------------------------------------------
//         if (argsStr.trim().length > 0) {
//             // var args = argsStr.split(/\s*,\s*/);
//             // result.args = args;
//             args = argsStr
//         }
//     };


//     print("createMessage")
//     print("args="+args)
//     print("returnType="+returnType);
//     print("funcName="+funcName)
//     print("from="+from)
//     print("to="+to)
//     createMessage(funcName, from, to, guard, args, assignVar, returnType, editor, LastSource, outPutY)

//     // return result;
// }

function createMessageProcess(line, editor, LastSource, ll, outPutY) {

    print("createMessageProcess start");

    var from = "";
    var to = "";
    var guard = "";
    var assignVar = "";
    var funcName = "";
    var args = "";
    var returnType = "";

    //---------------------------------------------------------
    // from → to 抽出
    //---------------------------------------------------------
    var ft = line.match(/(\w+)\s*->\s*(\w+)\s*:/);
    if (!ft) return null;
    from = ft[1];
    to = ft[2];

    //---------------------------------------------------------
    // 一番最初のコロン以降を取得
    //---------------------------------------------------------
    var idx = line.indexOf(":");
    var afterColon = line.substring(idx + 1).trim();

    //---------------------------------------------------------
    // 戻り値格納変数（ret = ...）
    //---------------------------------------------------------
    var assignMatch = afterColon.match(/^(\w+)\s*=\s*(.*)$/);
    if (assignMatch) {
        assignVar = assignMatch[1];
        afterColon = assignMatch[2].trim();
    }

    //---------------------------------------------------------
    // メッセージID [msg1.x]
    //---------------------------------------------------------
    var msgIdMatch = afterColon.match(/^\[(msg[^\]]+)\]/);
    if (msgIdMatch) {
        guard = msgIdMatch[1];
        afterColon = afterColon.replace(/^\[(msg[^\]]+)\]/, "").trim();
    }

    //---------------------------------------------------------
    // 関数呼び出し sub_func(...) : type
    //---------------------------------------------------------
    // sub():void に対応（非貪欲）
    var funcMatch = afterColon.match(/^(\w+)\s*\((.*?)\)\s*:(\w+)\s*$/);

    if (funcMatch) {
        funcName = funcMatch[1];
        args = funcMatch[2] ? funcMatch[2].trim() : "";
        returnType = funcMatch[3];
    }
    else{
        //---------------------------------------------------------
        // 関数呼び出しでない場合 → 代入メッセージパターン
        // 例: a = 1
        //---------------------------------------------------------
        var assignOnly = afterColon.match(/^(\w+)\s*=/);
        if (assignOnly) {
            funcName = assignOnly[1];  // "a"
            args = "";
            returnType = "";
            assignVar = "";            // ret=xxx ではない
        } else {
            //-----------------------------------------------------
            // その他（想定外だが funcName を空にして返す）
            //-----------------------------------------------------
            funcName = "";
            args = "";
            returnType = "";
        }        
    }

    //---------------------------------------------------------
    // デバッグ出力
    //---------------------------------------------------------
    print("createMessage");
    print("funcName=" + funcName);
    print("args=" + args);
    print("returnType=" + returnType);
    print("assignVar=" + assignVar);
    print("guard=" + guard);
    print("from=" + from);
    print("to=" + to);

    //---------------------------------------------------------
    // 実際の作成処理
    //---------------------------------------------------------
    createMessage(funcName, from, to, guard, args, assignVar, returnType,
                  editor, LastSource, ll, outPutY);
    print("created")
}
function createLoop(gard, x, y, w, h, editor,LastSource,ll,outPutY)
{
    //https://members.change-vision.com/javadoc/astah-api/10_1_0/api/ja/doc/javadoc/com/change_vision/jude/api/inf/model/ICombinedFragment.html
    print("createLoop start")
    print("editor="+editor)
    print("x="+x)
    print("y="+y)
    print("w="+w)
    print("h="+h)
    var Point2D = Java.type("java.awt.geom.Point2D");
    temp2 = editor.createCombinedFragment("", "loop", new Point2D.Double(x, y-50), w, h-10);
    print("createLoop 1")
    var mdl = temp2.getModel();
    // print("isloop"+mdl.isLoop());
    var ops = mdl.getInteractionOperands()
    var op = ops[0];
    op.setGuard(gard); 
    print("createLoop end")
    return mdl
}
function createAlt(gard, x, y, w, h, editor,LastSource,ll,outPutY)
{
    //https://members.change-vision.com/javadoc/astah-api/10_1_0/api/ja/doc/javadoc/com/change_vision/jude/api/inf/model/ICombinedFragment.html
    var Point2D = Java.type("java.awt.geom.Point2D");
    temp2 = editor.createCombinedFragment("", "alt", new Point2D.Double(x, y-50), w, h-10);
    var mdl = temp2.getModel();
    // print("isloop"+mdl.isLoop());
    var ops = mdl.getInteractionOperands()
    var op = ops[0];
    op.setGuard(gard); 
    return mdl
}

function createMessage(method,src,dst,gard,arg,retvariable, retType, editor, LastSource, ll, outPutY)
{   
    //https://members.change-vision.com/javadoc/astah-api/10_1_0/api/ja/doc/javadoc/com/change_vision/jude/api/inf/model/IMessage.html#setGuard(java.lang.String)
    print("method="+method)
    print("src="+src)
    print("dst="+dst)
    print("outPutY="+outPutY)
    print("LastSource.get(src)="+LastSource.get(src))
    print("LastSource.get(dst)="+LastSource.get(dst))
    print("editor="+editor)
    var temp = editor.createMessage(method,LastSource.get(src),ll.get(dst),outPutY);
    LastSource.put(src,temp.getSource());
    print("cre")
    var mdl = temp.getModel();
    mdl.setGuard(gard);
    if( retvariable != "" ){
        mdl.setReturnValueVariable(retvariable);
    }
    if( arg != "" ){
        mdl.setArgument(arg);
    }
    if( retType != ""){
        mdl.setReturnValue(retType)
    }
    return outPutY;
}

function getXEndLifeLine(ll)
{
    var maxX=0;
    for each (var v in ll.values()) {
        var tmpX = v.getLocation().getX();
        // print(v.getLocation());
        if(maxX<tmpX)
        {
            maxX = tmpX;
        }
    }
    return maxX;
}
function createLifelines(file){
    var offset = 100;
    // 関数呼び出し
    var names = extractLifelines(file);

    // 返却用の Map（順序保持）
    var HashMap = Java.type("java.util.LinkedHashMap");
    var resultMap = new HashMap();

    with (new JavaImporter(com.change_vision.jude.api.inf.editor)) {
        // Edit the astah model
        TransactionManager.beginTransaction();
        var editor = astah.getDiagramEditorFactory().getSequenceDiagramEditor();

        // 出力
        var it = names.iterator();
        while (it.hasNext()) {
            // print(it.next());
            var str = it.next()
            ll=editor.createLifeline(str,offset)
            // Map に追加
            resultMap.put(str, ll);
                        
            offset +=400;
        }
        TransactionManager.endTransaction();
    }
    return resultMap;  // ★ 呼び出し元へ返す    
}

function extractLifelines(file) {
    var FileReader  = Java.type("java.io.FileReader");
    var BufferedReader = Java.type("java.io.BufferedReader");

    var br = new BufferedReader(new FileReader(file));
    var lifelines = new java.util.LinkedHashSet(); // 重複なし、順序保持

    try {
        var line;
        while ((line = br.readLine()) != null) {
            line = line.trim();

            // participant / actor / boundary / control / entity / database
            var p = line.match(/^(participant|actor|boundary|control|entity|database)\s+([^\s]+)/);
            if (p) {
                lifelines.add(p[2]);
                continue;
            }

            // メッセージ行: A -> B : xxx
            var msg = line.match(/^([^\s]+)\s*->\s*([^\s]+)\s*:/);
            if (msg) {
                lifelines.add(msg[1]);
                lifelines.add(msg[2]);
                continue;
            }
        }
    } finally {
        br.close();
    }

    return lifelines; // Java の Set を返す
}



function printFileLines(file) {
    var FileReader  = Java.type("java.io.FileReader");
    var BufferedReader = Java.type("java.io.BufferedReader");

    var br = new BufferedReader(new FileReader(file));
    try {
        var line;
        while ((line = br.readLine()) != null) {
            print(line);
        }
    } finally {
        br.close();
    }
}

function createSeqName( filename )
{
    var woext = filename.substring(0,filename.lastIndexOf('.'));
    print(woext)
    return woext
}
function showOpenFileDialog() {
    var JFileChooser = Java.type("javax.swing.JFileChooser");

    var chooser = new JFileChooser();
    chooser.setDialogTitle("ファイルを選択してください");

    var result = chooser.showOpenDialog(null);

    if (result == JFileChooser.APPROVE_OPTION) {
        var file = chooser.getSelectedFile();
        print("選択されたファイル: " + file.getAbsolutePath());
        return file;
    } else {
        print("キャンセルされました");
        return null;
    }
};


function getNewSeqDiagram(name){
    with (new JavaImporter(com.change_vision.jude.api.inf.editor)) {
        // Edit the astah model
        TransactionManager.beginTransaction();
        var editor = astah.getDiagramEditorFactory().getSequenceDiagramEditor();
        var newDgm = editor.createSequenceDiagram(astah.getProject(), name);
        TransactionManager.endTransaction();
        print('New Seq Diagram was created!');
    }
    return newDgm;
}
function isSupportedAstah() {
    var edition = astah.getAstahEdition();
    print('Your edition is ' + edition);
    if (edition == 'professional' || edition == 'UML') {
        return true;
    } else {
        return false;
    }
}