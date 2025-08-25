# -*- coding: utf-8 -*-

import sys
import os
import re
import uuid
import keyword
import datetime
import tempfile
import subprocess

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPlainTextEdit, QTextEdit, QSplitter,
    QVBoxLayout, QHBoxLayout, QTabWidget, QLabel, QLineEdit, QPushButton,
    QCheckBox, QStatusBar, QToolBar, QFileDialog, QMessageBox, QMenu
)
from PyQt6.QtGui import (
    QSyntaxHighlighter, QTextCharFormat, QColor, QFont, QPainter,
    QTextCursor, QPalette, QKeySequence, QAction
)
from PyQt6.QtCore import (
    Qt, QRegularExpression, QSize, QRect, QTimer, QPoint
)

# ============= تبويب محرر متقدم (الكود الجديد المدمج) 3944 =============
class PythonSyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlightingRules = []
        self.setupRules()

    def setupRules(self):
        # تلوين الكلمات المفتاحية
        keywordFormat = QTextCharFormat()
        keywordFormat.setForeground(QColor('#569CD6'))
        keywords = '|'.join(keyword.kwlist)
        self.highlightingRules.append((QRegularExpression(f'\\b({keywords})\\b'), keywordFormat))

        # تلوين الأرقام
        numberFormat = QTextCharFormat()
        numberFormat.setForeground(QColor('#B5CEA8'))
        self.highlightingRules.append((QRegularExpression('\\b[0-9]+(?:\\.[0-9]+)?\\b'), numberFormat))

        # تلوين النصوص
        stringFormat = QTextCharFormat()
        stringFormat.setForeground(QColor('#CE9178'))
        self.highlightingRules.append((QRegularExpression('"[^"\\\\]*(\\\\.[^"\\\\]*)*"'), stringFormat))
        self.highlightingRules.append((QRegularExpression("'[^'\\\\]*(\\\\.[^'\\\\]*)*'"), stringFormat))
        self.highlightingRules.append((QRegularExpression('"""[^"]*"""'), stringFormat))
        self.highlightingRules.append((QRegularExpression("'''[^']*'''"), stringFormat))

        # تلوين التعليقات
        commentFormat = QTextCharFormat()
        commentFormat.setForeground(QColor('#6A9955'))
        self.highlightingRules.append((QRegularExpression('#[^\\n]*'), commentFormat))

        # تلوين الدوال والكلاسات
        functionFormat = QTextCharFormat()
        functionFormat.setForeground(QColor('#DCDCAA'))
        self.highlightingRules.append((QRegularExpression('\\bdef\\s+(\\w+)\\s*\\('), functionFormat))
        self.highlightingRules.append((QRegularExpression('\\bclass\\s+(\\w+)\\s*[:(]'), functionFormat))

        # تلوين self
        selfFormat = QTextCharFormat()
        selfFormat.setForeground(QColor('#9CDCFE'))
        self.highlightingRules.append((QRegularExpression('\\bself\\b'), selfFormat))

    def highlightBlock(self, text):
        for pattern, format in self.highlightingRules:
            matchIterator = pattern.globalMatch(text)
            while matchIterator.hasNext():
                match = matchIterator.next()
                start = match.capturedStart()
                length = match.capturedLength()
                if pattern.pattern() in ('\\bdef\\s+(\\w+)\\s*\\(', '\\bclass\\s+(\\w+)\\s*[:(]'):
                    start = match.capturedStart(1)
                    length = match.capturedLength(1)
                self.setFormat(start, length, format)

        self.setCurrentBlockState(0)
        startIndex = 0
        if self.previousBlockState() != 1:
            startIndex = text.find('"""')
            if startIndex == -1:
                startIndex = text.find("'''")

        while startIndex >= 0:
            endIndexTripleDouble = text.find('"""', startIndex + 3)
            endIndexTripleSingle = text.find("'''", startIndex + 3)

            if text.startswith('"""', startIndex):
                quote_len = 3
                endIndex = endIndexTripleDouble
            elif text.startswith("'''", startIndex):
                 quote_len = 3
                 endIndex = endIndexTripleSingle
            else:
                break

            if endIndex == -1:
                self.setCurrentBlockState(1)
                commentLength = len(text) - startIndex
            else:
                commentLength = endIndex - startIndex + quote_len
                self.setCurrentBlockState(0)

            stringFormat = QTextCharFormat()
            stringFormat.setForeground(QColor('#CE9178'))
            self.setFormat(startIndex, commentLength, stringFormat)
            
            nextTripleDouble = text.find('"""', startIndex + commentLength)
            nextTripleSingle = text.find("'''", startIndex + commentLength)
            if nextTripleDouble == -1 and nextTripleSingle == -1:
                startIndex = -1
            elif nextTripleDouble == -1:
                startIndex = nextTripleSingle
            elif nextTripleSingle == -1:
                 startIndex = nextTripleDouble
            else:
                 startIndex = min(nextTripleDouble, nextTripleSingle)

class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self._main_window = editor.window()
        self._font_metrics = self.fontMetrics()

    def sizeHint(self):
        return QSize(self.editor.lineNumberAreaWidth(), 0)

    def paintEvent(self, event):
        self.editor.lineNumberAreaPaintEvent(event)

    def updateFontMetrics(self):
        self._font_metrics = self.fontMetrics()

class TextEditWithLineNumbers(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.lineNumberArea = LineNumberArea(self)
        self._main_window = self.window()
        self._bracket_match_positions = []
        self._bracket_format = QTextCharFormat()
        
        self.blockCountChanged.connect(self.updateLineNumberAreaWidth)
        self.updateRequest.connect(self.updateLineNumberArea)
        self.cursorPositionChanged.connect(self.highlightCurrentLine)
        self.cursorPositionChanged.connect(self.matchBrackets)

        self.updateLineNumberAreaWidth(0)
        self.highlightCurrentLine()
        
    def set_dark_mode(self, is_dark):
        self._bracket_format.setBackground(QColor(80, 80, 80, 150) if is_dark else QColor(200, 200, 200, 150))
        self._bracket_format.setFontWeight(QFont.Weight.Bold)

    def lineNumberAreaWidth(self):
        digits = 1
        max_num = max(1, self.blockCount())
        while max_num >= 10:
            max_num /= 10
            digits += 1
        space = 10 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

    def updateLineNumberAreaWidth(self, _=None):
        self.setViewportMargins(self.lineNumberAreaWidth(), 0, 0, 0)

    def updateLineNumberArea(self, rect, dy):
        if dy:
            self.lineNumberArea.scroll(0, dy)
        else:
            self.lineNumberArea.update(0, rect.y(), self.lineNumberArea.width(), rect.height())

        if rect.contains(self.viewport().rect()):
            self.updateLineNumberAreaWidth(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.lineNumberArea.setGeometry(QRect(cr.left(), cr.top(), self.lineNumberAreaWidth(), cr.height()))

    def lineNumberAreaPaintEvent(self, event):
        is_dark = self._main_window.is_dark_mode if self._main_window and hasattr(self._main_window, 'is_dark_mode') else False

        painter = QPainter(self.lineNumberArea)
        bg_color = QColor('#333333') if is_dark else QColor('#EEEEEE')
        painter.fillRect(event.rect(), bg_color)

        block = self.firstVisibleBlock()
        blockNumber = block.blockNumber()
        font_metrics = self.fontMetrics()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        bottom = top + self.blockBoundingRect(block).height()

        height = font_metrics.height()
        width = self.lineNumberArea.width()
        num_margin = 5

        pen_color = QColor('#888888') if is_dark else QColor('#666666')
        painter.setPen(pen_color)

        font = painter.font()
        painter.setFont(font)

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(blockNumber + 1)
                painter.drawText(0, int(top), width - num_margin, height,
                                 Qt.AlignmentFlag.AlignRight, number)

            block = block.next()
            if not block.isValid():
                break
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()
            blockNumber += 1

    def highlightCurrentLine(self):
        extraSelections = []

        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            is_dark = self._main_window.is_dark_mode if self._main_window and hasattr(self._main_window, 'is_dark_mode') else False
            lineColor = QColor(51, 51, 51) if is_dark else QColor(232, 232, 232)
            selection.format.setBackground(lineColor)
            selection.format.setProperty(QTextCharFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extraSelections.append(selection)

        for pos, length in self._bracket_match_positions:
             sel = QTextEdit.ExtraSelection()
             sel.format = self._bracket_format
             sel.cursor = self.textCursor()
             sel.cursor.setPosition(pos)
             sel.cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, length)
             extraSelections.append(sel)
        
        # Keep search highlights
        current_extra_selections = self.extraSelections()
        for sel in current_extra_selections:
             if sel.format.property(QTextCharFormat.Property.UserProperty) == "search_highlight":
                 extraSelections.append(sel)

        self.setExtraSelections(extraSelections)

    def setFont(self, font):
        super().setFont(font)
        if hasattr(self, 'lineNumberArea'):
            self.lineNumberArea.updateFontMetrics()
            self.updateLineNumberAreaWidth()

    def keyPressEvent(self, event):
        cursor = self.textCursor()
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            block = cursor.block()
            line_text = block.text()
            indentation = ""
            for char in line_text:
                if char.isspace():
                    indentation += char
                else:
                    break

            cursor.insertText("\n" + indentation)

            prev_char_pos = cursor.position() - len(indentation) - 2
            if prev_char_pos >= block.position():
                 prev_char_cursor = QTextCursor(self.document())
                 prev_char_cursor.setPosition(prev_char_pos)
                 prev_char_cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 1)
                 if prev_char_cursor.selectedText().strip() == ':':
                      cursor.insertText("    ")
            self.ensureCursorVisible()
            event.accept()
        else:
            super().keyPressEvent(event)

    def matchBrackets(self):
        self._bracket_match_positions = []
        cursor = self.textCursor()
        pos = cursor.position()
        doc = self.document()

        if pos > 0:
            char_before = doc.characterAt(pos - 1)
            match_pos = self._findMatchingBracket(pos - 1, char_before)
            if match_pos is not None:
                 self._bracket_match_positions.append((pos - 1, 1))
                 self._bracket_match_positions.append((match_pos, 1))

        if pos < doc.characterCount():
             char_at = doc.characterAt(pos)
             match_pos = self._findMatchingBracket(pos, char_at)
             if match_pos is not None:
                  if not self._bracket_match_positions:
                      self._bracket_match_positions.append((pos, 1))
                      self._bracket_match_positions.append((match_pos, 1))

        self.highlightCurrentLine()

    def _findMatchingBracket(self, position, char):
        brackets = {'(': ')', ')': '(', '[': ']', ']': '[', '{': '}', '}': '{'}
        if char not in brackets:
            return None

        match_char = brackets[char]
        doc = self.document()
        search_cursor = QTextCursor(doc)
        search_cursor.setPosition(position)

        if char in "([{":
            direction = QTextCursor.MoveOperation.NextCharacter
            level = 1
            limit = doc.characterCount()
            current_pos = position + 1
        else:
            direction = QTextCursor.MoveOperation.PreviousCharacter
            level = 1
            limit = -1
            current_pos = position - 1

        while current_pos != limit:
            current_char = doc.characterAt(current_pos)
            if current_char == match_char:
                level -= 1
                if level == 0:
                    return current_pos
            elif current_char == char:
                level += 1

            if direction == QTextCursor.MoveOperation.NextCharacter:
                current_pos += 1
            else:
                current_pos -= 1

        return None

class EditorPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.current_file = None
        self.is_dark_mode = self.main_window.is_dark_mode
        self.create_widgets()
    
    def create_widgets(self):
        self.textEdit = TextEditWithLineNumbers(parent=self)
        self.textEdit.setFont(QFont("Consolas", 12))
        self.textEdit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.highlighter = PythonSyntaxHighlighter(self.textEdit.document())
        
        self.outputConsole = QPlainTextEdit()
        self.outputConsole.setFont(QFont("Consolas", 11))
        self.outputConsole.setReadOnly(True)
        self.outputConsole.setPlaceholderText("سيظهر إخراج الكود هنا...")

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.addWidget(self.textEdit)
        self.splitter.addWidget(self.outputConsole)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([600, 200])

        layout = QVBoxLayout()
        layout.addWidget(self.splitter)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        self.textEdit.textChanged.connect(self.main_window.update_current_tab_title)
        self.textEdit.cursorPositionChanged.connect(self.main_window.updateLineColStatus)

class AdvancedEditorTab(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("محرر نصوص متقدم - الإصدار الذهبي 🏆")
        self.setGeometry(100, 100, 1280, 860)

        self.is_dark_mode = True
        self.search_positions = []
        self.search_index = -1
        
        self.createWidgets()
        self.createToolbars()
        self.createStatusBar()
        self.createMenus()
        self.setupShortcuts()

        self.applyTheme()
        
        self.new_tab(is_welcome_tab=True)
        self.updateLineColStatus()
    
    def active_editor_page(self) -> EditorPage | None:
        if self.tab_widget.count() > 0:
            return self.tab_widget.currentWidget()
        return None

    def createWidgets(self):
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        self.tab_widget.currentChanged.connect(self.on_tab_changed)

        self.searchBar = QWidget()
        searchLayout = QHBoxLayout()
        searchLayout.setContentsMargins(2, 5, 2, 5)

        self.searchLabel = QLabel("بحث:")
        self.searchEntry = QLineEdit()
        self.searchEntry.setPlaceholderText("ابحث هنا...")
        self.searchEntry.setMinimumWidth(150)
        self.searchEntry.returnPressed.connect(self.performSearch)

        self.replaceLabel = QLabel("استبدال:")
        self.replaceEntry = QLineEdit()
        self.replaceEntry.setPlaceholderText("استبدل بـ...")
        self.replaceEntry.setMinimumWidth(150)

        self.findBtn = QPushButton("بحث")
        self.findPrevBtn = QPushButton("السابق")
        self.findNextBtn = QPushButton("التالي")
        self.replaceBtn = QPushButton("استبدال")
        self.replaceAllBtn = QPushButton("استبدال الكل")
        self.cancelSearchBtn = QPushButton("إلغاء")

        self.caseSensitiveCheck = QCheckBox("حساس لحالة الأحرف")
        self.wholeWordCheck = QCheckBox("كلمة كاملة")

        searchLayout.addWidget(self.searchLabel)
        searchLayout.addWidget(self.searchEntry)
        searchLayout.addWidget(self.findBtn)
        searchLayout.addWidget(self.findPrevBtn)
        searchLayout.addWidget(self.findNextBtn)
        searchLayout.addWidget(self.caseSensitiveCheck)
        searchLayout.addWidget(self.wholeWordCheck)
        searchLayout.addStretch(1)
        searchLayout.addWidget(self.replaceLabel)
        searchLayout.addWidget(self.replaceEntry)
        searchLayout.addWidget(self.replaceBtn)
        searchLayout.addWidget(self.replaceAllBtn)
        searchLayout.addWidget(self.cancelSearchBtn)

        self.searchBar.setLayout(searchLayout)
        self.searchBar.hide()

        centralWidget = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(self.searchBar)
        layout.addWidget(self.tab_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        centralWidget.setLayout(layout)
        self.setCentralWidget(centralWidget)

        self.findBtn.clicked.connect(lambda: self.performSearch(search_forward=True))
        self.findNextBtn.clicked.connect(self.nextResult)
        self.findPrevBtn.clicked.connect(self.prevResult)
        self.replaceBtn.clicked.connect(self.replaceOne)
        self.replaceAllBtn.clicked.connect(self.replaceAll)
        self.cancelSearchBtn.clicked.connect(lambda: (self.clearSearchHighlight(), self.searchBar.hide(), self.active_editor_page().textEdit.setFocus() if self.active_editor_page() else None))
        self.caseSensitiveCheck.stateChanged.connect(lambda: self.performSearch(search_forward=True) if self.searchEntry.text() else None)
        self.wholeWordCheck.stateChanged.connect(lambda: self.performSearch(search_forward=True) if self.searchEntry.text() else None)

    def createToolbars(self):
        self.toolbar = QToolBar("أدوات رئيسية")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)

        actions = [ 
            ("لسان تبويب جديد", "Ctrl+T", self.new_tab), 
            ("فتح", "Ctrl+O", self.openFile),
            ("💾", "Ctrl+S", self.saveFile),
            ("حفظ باسم", "Ctrl+Shift+S", self.saveAs),
            ("حفظ عشوائي (.py)", "", lambda: self.saveRandomFile(".py")),
            ("---", "", None),
            ("تراجع", "Ctrl+Z", lambda: self.active_editor_page().textEdit.undo() if self.active_editor_page() else None),
            ("إعادة", "Ctrl+Y", lambda: self.active_editor_page().textEdit.redo() if self.active_editor_page() else None),
            ("---", "", None),
            ("✂️", "Ctrl+X", self.cut),
            ("📋", "Ctrl+C", self.copy),
            ("📥", "Ctrl+V", self.paste),
            ("---", "", None),
            ("🔍", "Ctrl+F", self.toggleSearchBar),
            ("#", "Ctrl+/", self.toggleComment),
            ("▶️💻", "F5", self.runCode),
            ("---", "", None),
            ("📚📊", "", self.analyzeImports),
            ("---", "", None),
            ("🗑️", "", self.clearContent),
            ("🗑️ثم📥", "", self.clearAndPaste),
            ("🎯ثم🗑️ثم📥", "", self.focus_clear_and_paste),
            ("🗑️/📥/💾", "", self.clearPasteAndSaveRandom),
            ("---", "", None),
            ("🌗", "", self.toggleTheme)
        ]

        for text, shortcut, callback in actions:
            if text == "---":
                self.toolbar.addSeparator()
                continue
            action = QAction(text, self)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            if callback:
                action.triggered.connect(callback)
            self.toolbar.addAction(action)
        
        select_all_text_action = QAction("تحديد الكل", self)
        select_all_text_action.setToolTip("تحديد كل المحتوى في المحرر الرئيسي")
        select_all_text_action.triggered.connect(self.select_editor_text)
        paste_action = next((a for a in self.toolbar.actions() if a.text() == "📥"), None)
        if paste_action:
            self.toolbar.insertAction(paste_action.menu().actions()[0] if paste_action.menu() else paste_action, select_all_text_action)
            self.toolbar.insertSeparator(paste_action.menu().actions()[0] if paste_action.menu() else paste_action)

        self.toolbar.addSeparator()
        self.toggle_output_action = QAction("إخفاء الإخراج", self)
        self.toggle_output_action.setToolTip("تبديل إظهار/إخفاء منطقة الإخراج (F6)")
        self.toggle_output_action.setCheckable(True)
        self.toggle_output_action.setChecked(True)
        self.toggle_output_action.setShortcut(QKeySequence("F6"))
        self.toggle_output_action.triggered.connect(self.handleOutputToggle)
        self.toolbar.addAction(self.toggle_output_action)

        self.toolbar.addSeparator()
        clear_output_action = QAction("مسح الإخراج", self)
        clear_output_action.triggered.connect(lambda: self.active_editor_page().outputConsole.clear() if self.active_editor_page() else None)
        self.toolbar.addAction(clear_output_action)

        copy_output_action = QAction("نسخ الإخراج", self)
        copy_output_action.triggered.connect(self.copy_output_text)
        self.toolbar.addAction(copy_output_action)

    def copy_output_text(self):
        page = self.active_editor_page()
        if not page:
            self.updateStatusBar("لا يوجد لسان تبويب نشط لنسخ الإخراج منه.")
            return

        output_text = page.outputConsole.toPlainText()
        if output_text:
            clipboard = QApplication.clipboard()
            clipboard.setText(output_text)
            self.updateStatusBar("تم نسخ محتوى الإخراج إلى الحافظة.")
        else:
            self.updateStatusBar("لا يوجد نص في الإخراج لنسخه.")

    def focus_clear_and_paste(self):
        page = self.active_editor_page()
        if page:
            page.textEdit.setFocus()
            page.textEdit.clear()
            QTimer.singleShot(10, page.textEdit.paste)

    def createStatusBar(self):
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusLabel = QLabel("جاهز")
        self.statusBar.addWidget(self.statusLabel, 1)

        self.lineColLabel = QLabel("Ln 1, Col 1")
        self.lineColLabel.setMinimumWidth(100)
        self.lineColLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.statusBar.addPermanentWidget(self.lineColLabel)

    def updateStatusBar(self, message, timeout=4000):
        self.statusLabel.setText(message)
        self.statusBar.showMessage(message, timeout)

    def updateLineColStatus(self):
        page = self.active_editor_page()
        if page:
            cursor = page.textEdit.textCursor()
            line = cursor.blockNumber() + 1
            col = cursor.columnNumber() + 1
            self.lineColLabel.setText(f"Ln {line}, Col {col}")
        else:
            self.lineColLabel.setText("")

    def createMenus(self):
        self.menuBar().clear()

        file_menu = self.menuBar().addMenu("ملف")
        file_actions_texts = ["لسان تبويب جديد", "فتح", "💾", "حفظ باسم", "حفظ عشوائي (.py)"]
        file_actions = [a for a in self.toolbar.actions() if a.text() in file_actions_texts]
        for action in file_actions:
            file_menu.addAction(action)
        file_menu.addSeparator()
        exit_action = QAction("خروج", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        edit_menu = self.menuBar().addMenu("تحرير")
        edit_actions_texts = ["تراجع", "إعادة", "✂️", "📋", "📥", "🔍", "#", "🗑️"]
        edit_actions = [a for a in self.toolbar.actions() if a.text() in edit_actions_texts]
        for action in edit_actions:
            edit_menu.addAction(action)
        edit_menu.addSeparator()
        select_all_action = QAction("تحديد الكل", self)
        select_all_action.setShortcut("Ctrl+A")
        select_all_action.triggered.connect(self.selectAll)
        edit_menu.addAction(select_all_action)
        
        view_menu = self.menuBar().addMenu("عرض")
        view_menu.addAction(self.toggle_output_action)
        theme_action_text = "🌗"
        theme_action = next((a for a in self.toolbar.actions() if a.text() == theme_action_text), None)
        if theme_action:
            view_menu.addAction(theme_action)
            
        run_menu = self.menuBar().addMenu("تشغيل")
        run_actions_texts = ["▶️💻", "📚📊"]
        run_actions = [a for a in self.toolbar.actions() if a.text() in run_actions_texts]
        for action in run_actions:
            run_menu.addAction(action)

    def setupShortcuts(self):
        shortcuts = [
            ("F3", self.nextResult),
            ("Shift+F3", self.prevResult),
            ("Esc", lambda: (self.clearSearchHighlight(), self.searchBar.hide(), self.active_editor_page().textEdit.setFocus() if self.searchBar.isVisible() and self.active_editor_page() else None)),
        ]

        for key, callback in shortcuts:
            action = QAction(self)
            action.setShortcut(QKeySequence(key))
            if callback:
                action.triggered.connect(callback)
            self.addAction(action)

    def handleOutputToggle(self, checked):
        page = self.active_editor_page()
        if not page: return

        if checked:
            page.outputConsole.show()
            self.toggle_output_action.setText("إخفاء الإخراج")
            self.updateStatusBar("تم إظهار منطقة الإخراج.")
        else:
            page.outputConsole.hide()
            self.toggle_output_action.setText("إظهار الإخراج")
            self.updateStatusBar("تم إخفاء منطقة الإخراج.")

    def toggleTheme(self):
        self.is_dark_mode = not self.is_dark_mode
        self.applyTheme()
        if self.search_positions:
            self.highlightSearchResults()

    def applyTheme(self):
        app = QApplication.instance()
        palette = QPalette()

        if self.is_dark_mode:
            bg_color = QColor(30, 30, 30)
            text_color = QColor(220, 220, 220)
            window_color = QColor(46, 46, 46)
            button_color = QColor(60, 63, 65)
            highlight_color = QColor(42, 130, 218)
            highlighted_text_color = Qt.GlobalColor.white
            output_bg_color = QColor(25, 25, 25)
            output_text_color = QColor(220, 220, 220)
            disabled_text_color = QColor(128, 128, 128)
            placeholder_color = QColor(80, 80, 80)
            
            palette.setColor(QPalette.ColorRole.Window, window_color)
            palette.setColor(QPalette.ColorRole.WindowText, text_color)
            palette.setColor(QPalette.ColorRole.Base, bg_color)
            palette.setColor(QPalette.ColorRole.AlternateBase, QColor(45, 45, 45))
            palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.black)
            palette.setColor(QPalette.ColorRole.Text, text_color)
            palette.setColor(QPalette.ColorRole.Button, button_color)
            palette.setColor(QPalette.ColorRole.ButtonText, text_color)
            palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
            palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
            palette.setColor(QPalette.ColorRole.Highlight, highlight_color)
            palette.setColor(QPalette.ColorRole.HighlightedText, highlighted_text_color)
            palette.setColor(QPalette.ColorRole.PlaceholderText, placeholder_color)
            palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled_text_color)
            palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled_text_color)
            palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled_text_color)
            palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.PlaceholderText, placeholder_color.darker(120))
        else:
            app.setStyle("Fusion")
            palette = app.style().standardPalette()
            output_bg_color = QColor(248, 248, 248)
            output_text_color = QColor(50, 50, 50)
        
        app.setPalette(palette)
        
        for i in range(self.tab_widget.count()):
            page = self.tab_widget.widget(i)
            self.applyTheme_to_page(page)

        self.updateStatusBar(f"تم التبديل إلى الوضع {'الداكن' if self.is_dark_mode else 'الفاتح'}")

    def update_current_tab_title(self):
        page = self.active_editor_page()
        if page:
            index = self.tab_widget.currentIndex()
            title = "ملف جديد"
            if page.current_file:
                title = os.path.basename(page.current_file)
            
            if page.textEdit.document().isModified():
                title += "*"
            
            self.tab_widget.setTabText(index, title)

    def insertSampleContent(self, page):
        sample_code = """import os
import sys
import datetime
from collections import Counter
# import numpy as np

# Get current time
now = datetime.datetime.now()

print(f"Python Version: {sys.version}")
print(f"OS Name: {os.name}")
print(f"Current Time: {now.strftime('%Y-%m-%d %H:%M:%S')}")

def greet(name: str) -> None:
    '''Greets the user.'''
    print(f"Hello, {name}!")

greet("User")
"""
        page.textEdit.setPlainText(sample_code)
        page.textEdit.document().setModified(False)
        self.update_current_tab_title()
        page.outputConsole.clear()
        page.outputConsole.setPlainText("مرحباً! اضغط F5 لتشغيل الكود أو زر 'تحليل المكتبات' لرؤية المكتبات المستخدمة.")

    def new_tab(self, is_welcome_tab=False):
        page = EditorPage(self)
        self.applyTheme_to_page(page)
        
        if is_welcome_tab:
            self.insertSampleContent(page)

        page.textEdit.document().setModified(False)

        index = self.tab_widget.addTab(page, "ملف جديد")
        self.tab_widget.setCurrentIndex(index)
        self.update_current_tab_title()
        
        page.textEdit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        page.textEdit.customContextMenuRequested.connect(self.showTextContextMenu)
        page.outputConsole.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        page.outputConsole.customContextMenuRequested.connect(self.showOutputContextMenu)
        
        return page

    def on_tab_changed(self, index):
        self.updateLineColStatus()
        page = self.active_editor_page()
        if page:
            output_visible = not page.outputConsole.isHidden()
            self.toggle_output_action.setChecked(output_visible)
            self.toggle_output_action.setText("إخفاء الإخراج" if output_visible else "إظهار الإخراج")
        self.clearSearchHighlight(show_message=False)

    def close_tab(self, index):
        page = self.tab_widget.widget(index)
        if page.textEdit.document().isModified():
            self.tab_widget.setCurrentIndex(index)
            reply = QMessageBox.question(self, 'إغلاق لسان التبويب',
                                         f"يوجد تغييرات لم يتم حفظها في الملف '{self.tab_widget.tabText(index).replace('*','')}'.\nهل تريد حفظها قبل الإغلاق؟",
                                         QMessageBox.StandardButton.Save |
                                         QMessageBox.StandardButton.Discard |
                                         QMessageBox.StandardButton.Cancel,
                                         QMessageBox.StandardButton.Save)

            if reply == QMessageBox.StandardButton.Save:
                if not self.saveFile():
                    return # Don't close if save is cancelled
            elif reply == QMessageBox.StandardButton.Cancel:
                return
        
        self.tab_widget.removeTab(index)
        if self.tab_widget.count() == 0:
            self.close()

    def applyTheme_to_page(self, page):
        page.is_dark_mode = self.is_dark_mode
        page.textEdit.set_dark_mode(self.is_dark_mode)

        palette = self.palette()
        output_palette = QPalette(palette)
        if self.is_dark_mode:
            output_bg_color = QColor(25, 25, 25)
            output_text_color = QColor(220, 220, 220)
            output_palette.setColor(QPalette.ColorRole.Base, output_bg_color)
            output_palette.setColor(QPalette.ColorRole.Text, output_text_color)
        else:
            output_palette.setColor(QPalette.ColorRole.Base, QColor(248, 248, 248))
            output_palette.setColor(QPalette.ColorRole.Text, QColor(50, 50, 50))
            
        page.outputConsole.setPalette(output_palette)
        page.highlighter.rehighlight()
        page.textEdit.lineNumberArea.update()
        page.textEdit.highlightCurrentLine()


    def openFile(self):
        filepaths, _ = QFileDialog.getOpenFileNames(self, "فتح ملفات", "", "ملفات بايثون (*.py);;ملفات نصية (*.txt);;كل الملفات (*)")
        for filepath in filepaths:
            if filepath:
                for i in range(self.tab_widget.count()):
                    page = self.tab_widget.widget(i)
                    if page.current_file == filepath:
                        self.tab_widget.setCurrentIndex(i)
                        return

                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    page = self.new_tab()
                    page.textEdit.blockSignals(True)
                    page.textEdit.setPlainText(content)
                    page.textEdit.blockSignals(False)
                    page.current_file = filepath
                    page.textEdit.document().setModified(False)
                    
                    self.update_current_tab_title()
                    self.updateStatusBar(f"تم فتح الملف: {os.path.basename(filepath)}")
                    page.textEdit.moveCursor(QTextCursor.MoveOperation.Start)
                    page.textEdit.ensureCursorVisible()
                    page.textEdit.updateLineNumberAreaWidth()
                    page.outputConsole.clear()

                except Exception as e:
                    QMessageBox.critical(self, "خطأ", f"لا يمكن فتح الملف:\n{e}")
                    self.updateStatusBar(f"فشل فتح الملف: {os.path.basename(filepath)}")

    def saveFile(self):
        page = self.active_editor_page()
        if not page: return False
        
        if not page.textEdit.document().isModified() and page.current_file:
            self.updateStatusBar(f"الملف '{os.path.basename(page.current_file)}' غير معدل.")
            return True

        if page.current_file:
            return self._saveToFile(page, page.current_file)
        else:
            return self.saveAs()

    def saveAs(self):
        page = self.active_editor_page()
        if not page: return False

        filepath, _ = QFileDialog.getSaveFileName(self, "حفظ باسم", page.current_file or "untitled.py", "ملفات بايثون (*.py);;ملفات نصية (*.txt);;كل الملفات (*)")
        if filepath:
            if self._saveToFile(page, filepath):
                page.current_file = filepath
                self.update_current_tab_title()
                return True
        return False

    def _saveToFile(self, page, filepath):
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(page.textEdit.toPlainText())
            page.textEdit.document().setModified(False)
            self.update_current_tab_title()
            self.updateStatusBar(f"تم الحفظ في: {os.path.basename(filepath)}")
            return True
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"لا يمكن حفظ الملف:\n{e}")
            self.updateStatusBar(f"فشل حفظ الملف: {os.path.basename(filepath)}")
            return False

    def cut(self):
        widget = self.focusWidget()
        if isinstance(widget, (QPlainTextEdit, QLineEdit)):
            widget.cut()

    def copy(self):
        widget = self.focusWidget()
        if isinstance(widget, (QPlainTextEdit, QLineEdit)):
            widget.copy()

    def paste(self):
        widget = self.focusWidget()
        if isinstance(widget, (QPlainTextEdit, QLineEdit)) and not widget.isReadOnly():
             widget.paste()

    def selectAll(self):
        widget = self.focusWidget()
        if isinstance(widget, (QPlainTextEdit, QLineEdit)):
            widget.selectAll()

    def select_editor_text(self):
        page = self.active_editor_page()
        if page:
            page.textEdit.selectAll()
            self.updateStatusBar("تم تحديد كل النص في المحرر.")
        else:
            self.updateStatusBar("لا يوجد محرر نشط لتحديد النص فيه.")

    def clearContent(self):
        page = self.active_editor_page()
        if not page: return
        widget_to_clear = self.focusWidget()
        
        if widget_to_clear == page.textEdit:
            confirm = QMessageBox.question(self, "تأكيد المسح",
                                           "هل أنت متأكد أنك تريد مسح كل المحتوى في المحرر؟",
                                           QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                           QMessageBox.StandardButton.No)
            if confirm == QMessageBox.StandardButton.Yes:
                page.textEdit.clear()
                self.updateStatusBar("تم مسح محتوى المحرر")
                self.clearSearchHighlight()
        elif widget_to_clear == page.outputConsole:
             page.outputConsole.clear()
             self.updateStatusBar("تم مسح محتوى منطقة الإخراج")
        elif isinstance(widget_to_clear, QLineEdit):
             widget_to_clear.clear()

    def clearAndPaste(self):
        page = self.active_editor_page()
        if page and self.focusWidget() == page.textEdit:
            page.textEdit.clear()
            QTimer.singleShot(10, page.textEdit.paste)
            self.updateStatusBar("لصق المحتوى")

    def saveRandomFile(self, extension=".py"):
        page = self.active_editor_page()
        if not page: return

        filename = f"temp_{uuid.uuid4().hex[:8]}{extension}"
        save_dir_options = [
            os.path.join(os.path.expanduser("~"), "Documents"),
            os.path.join(os.path.expanduser("~"), "Desktop"),
            os.getcwd()
        ]
        save_dir = next((d for d in save_dir_options if os.path.isdir(d)), os.getcwd())
        filepath = os.path.join(save_dir, filename)

        try:
            content = page.textEdit.toPlainText()
            if not content.strip():
                content = "# ملف بايثون مؤقت\nprint('مرحباً بالعالم!')"
                page.textEdit.setPlainText(content)

            if self._saveToFile(page, filepath):
                page.current_file = filepath
                self.update_current_tab_title()
                self.updateStatusBar(f"تم الحفظ العشوائي في: {filename}")
                self.openFileExternally(filepath)
            else:
                 raise Exception("Failed to save file using _saveToFile method.")
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"لا يمكن حفظ الملف العشوائي:\n{e}")
            self.updateStatusBar("فشل حفظ الملف العشوائي")

    def openFileExternally(self, filepath):
        try:
            if sys.platform == "win32": os.startfile(os.path.normpath(filepath))
            elif sys.platform == "darwin": subprocess.call(["open", filepath])
            else: subprocess.call(["xdg-open", filepath])
        except Exception as e:
            QMessageBox.warning(self, "تحذير", f"لا يمكن فتح الملف '{os.path.basename(filepath)}' خارجياً:\n{e}")

    def clearPasteAndSaveRandom(self):
        self.clearAndPaste()
        QTimer.singleShot(300, lambda: self.saveRandomFile(".py"))

    def toggleSearchBar(self):
        if not self.active_editor_page(): return
        if self.searchBar.isVisible():
            self.searchBar.hide()
            self.active_editor_page().textEdit.setFocus()
            self.clearSearchHighlight()
        else:
            self.searchBar.show()
            self.searchEntry.setFocus()
            self.searchEntry.selectAll()
            if self.searchEntry.text():
                self.performSearch()

    def _get_find_flags(self):
        find_flags = QTextDocument.FindFlag(0)
        if self.caseSensitiveCheck.isChecked():
            find_flags |= QTextDocument.FindFlag.FindCaseSensitively
        if self.wholeWordCheck.isChecked():
            find_flags |= QTextDocument.FindFlag.FindWholeWords
        return find_flags

    def performSearch(self, search_forward=True):
        page = self.active_editor_page()
        if not page: return
        query = self.searchEntry.text()
        if not query:
            self.clearSearchHighlight()
            return

        document = page.textEdit.document()
        cursor = page.textEdit.textCursor()
        find_flags = self._get_find_flags()

        self.search_positions = []
        search_cursor = QTextCursor(document)
        while True:
            search_cursor = document.find(query, search_cursor, find_flags)
            if search_cursor.isNull():
                break
            self.search_positions.append((search_cursor.selectionStart(), search_cursor.selectionEnd()))

        if not self.search_positions:
            self.updateStatusBar(f"لم يتم العثور على '{query}'")
            self.clearSearchHighlight(show_message=False)
            self.search_index = -1
            return

        current_pos = cursor.position()
        current_sel_start = cursor.selectionStart()

        new_search_index = -1

        if search_forward:
            search_start_point = current_sel_start if cursor.hasSelection() else current_pos
            found_after = False
            for i, (start, end) in enumerate(self.search_positions):
                if start >= search_start_point + (1 if cursor.hasSelection() and start == search_start_point else 0):
                    new_search_index = i
                    found_after = True
                    break
            if not found_after and self.search_positions:
                new_search_index = 0
        else:
            search_end_point = current_sel_start if cursor.hasSelection() else current_pos
            found_before = False
            for i in range(len(self.search_positions) - 1, -1, -1):
                start, end = self.search_positions[i]
                if end <= search_end_point:
                    new_search_index = i
                    found_before = True
                    break
            if not found_before and self.search_positions:
                 new_search_index = len(self.search_positions) - 1

        self.search_index = new_search_index

        self.highlightSearchResults()
        self.gotoSearchResult()
        if self.search_positions and self.search_index != -1:
             self.updateStatusBar(f"نتيجة {self.search_index + 1} من {len(self.search_positions)} لكلمة '{query}'", timeout=0)
        elif self.search_positions:
             self.updateStatusBar(f"تم العثور على {len(self.search_positions)} نتائج لكلمة '{query}', تحديد المؤشر...", timeout=0)

    def highlightSearchResults(self):
        page = self.active_editor_page()
        if not page: return
        page.textEdit.highlightCurrentLine() 
        extraSelections = page.textEdit.extraSelections()

        if not self.search_positions:
            return

        highlight_format = QTextCharFormat()
        current_highlight_format = QTextCharFormat()

        if self.is_dark_mode:
            highlight_color = QColor('#808000')
            current_highlight_color = QColor('#B8860B')
        else:
            highlight_color = QColor('#CCCC00')
            current_highlight_color = QColor('#FFD700')

        highlight_format.setBackground(highlight_color)
        highlight_format.setProperty(QTextCharFormat.Property.UserProperty, "search_highlight")

        current_highlight_format.setBackground(current_highlight_color)
        current_highlight_format.setProperty(QTextCharFormat.Property.UserProperty, "search_highlight")
        
        doc = page.textEdit.document()
        for i, (start, end) in enumerate(self.search_positions):
            selection = QTextEdit.ExtraSelection()
            selection.format = current_highlight_format if i == self.search_index else highlight_format
            selection.cursor = QTextCursor(doc)
            selection.cursor.setPosition(start)
            selection.cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            extraSelections.append(selection)

        page.textEdit.setExtraSelections(extraSelections)

    def gotoSearchResult(self):
        page = self.active_editor_page()
        if not page or not self.search_positions or not (0 <= self.search_index < len(self.search_positions)):
            return

        start, end = self.search_positions[self.search_index]
        cursor = page.textEdit.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)

        page.textEdit.setTextCursor(cursor)
        page.textEdit.ensureCursorVisible()
        self.highlightSearchResults()

    def nextResult(self):
        if not self.active_editor_page(): return
        if not self.searchEntry.text(): return

        if not self.search_positions:
            self.performSearch(search_forward=True)
            return

        if self.search_positions:
            self.search_index = (self.search_index + 1) % len(self.search_positions)
            self.gotoSearchResult()
            query = self.searchEntry.text()
            self.updateStatusBar(f"نتيجة {self.search_index + 1} من {len(self.search_positions)} لكلمة '{query}'", timeout=0)

    def prevResult(self):
        if not self.active_editor_page(): return
        if not self.searchEntry.text(): return
        
        if not self.search_positions:
            self.performSearch(search_forward=False)
            return

        if self.search_positions:
            self.search_index = (self.search_index - 1 + len(self.search_positions)) % len(self.search_positions)
            self.gotoSearchResult()
            query = self.searchEntry.text()
            self.updateStatusBar(f"نتيجة {self.search_index + 1} من {len(self.search_positions)} لكلمة '{query}'", timeout=0)

    def replaceOne(self):
        page = self.active_editor_page()
        if not page: return
        query = self.searchEntry.text()
        replacement = self.replaceEntry.text()

        if not query:
            self.updateStatusBar("يرجى إدخال نص البحث أولاً")
            return

        cursor = page.textEdit.textCursor()
        find_flags = self._get_find_flags()

        is_current_search_result_selected = False
        if cursor.hasSelection() and 0 <= self.search_index < len(self.search_positions):
            current_start, current_end = self.search_positions[self.search_index]
            text_to_compare = cursor.selectedText()
            query_to_compare = query
            if not (find_flags & QTextDocument.FindFlag.FindCaseSensitively):
                 text_to_compare = text_to_compare.lower()
                 query_to_compare = query_to_compare.lower()

            if (cursor.selectionStart() == current_start and
                cursor.selectionEnd() == current_end and
                text_to_compare == query_to_compare):
                 is_current_search_result_selected = True

        if is_current_search_result_selected:
            cursor.insertText(replacement)
            self.updateStatusBar(f"تم استبدال '{query}' بـ '{replacement}'")
            new_cursor_pos = cursor.position()
            self.clearSearchHighlight(show_message=False)
            QTimer.singleShot(0, lambda: self.performSearchFrom(new_cursor_pos))
        else:
            self.nextResult()

    def performSearchFrom(self, start_pos):
        page = self.active_editor_page()
        if not page: return
        cursor = page.textEdit.textCursor()
        cursor.setPosition(start_pos)
        page.textEdit.setTextCursor(cursor)
        self.performSearch(search_forward=True)

    def replaceAll(self):
        page = self.active_editor_page()
        if not page: return
        query = self.searchEntry.text()
        replacement = self.replaceEntry.text()

        if not query:
            self.updateStatusBar("يرجى إدخال نص البحث أولاً")
            return

        document = page.textEdit.document()
        find_flags = self._get_find_flags()
        count = 0

        temp_positions = []
        search_cursor = QTextCursor(document)
        while True:
            search_cursor = document.find(query, search_cursor, find_flags)
            if search_cursor.isNull(): break
            temp_positions.append((search_cursor.selectionStart(), search_cursor.selectionEnd()))

        if not temp_positions:
            self.updateStatusBar(f"لم يتم العثور على '{query}' للاستبدال")
            self.clearSearchHighlight()
            return

        page.textEdit.textCursor().beginEditBlock()
        cursor = QTextCursor(document)
        try:
            for start, end in reversed(temp_positions):
                cursor.setPosition(start)
                cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
                cursor.insertText(replacement)
                count += 1
        finally:
             page.textEdit.textCursor().endEditBlock()

        if count > 0:
            self.updateStatusBar(f"تم استبدال {count} نتيجة لكلمة '{query}'")
            self.clearSearchHighlight()
        else:
            self.updateStatusBar(f"لم يتم العثور على '{query}' للاستبدال")
            self.clearSearchHighlight()

    def clearSearchHighlight(self, show_message=True):
        page = self.active_editor_page()
        if not page: return
        page.textEdit.highlightCurrentLine() 
        self.search_positions = []
        self.search_index = -1

        if show_message and self.statusBar.currentMessage().startswith("نتيجة"):
            self.updateStatusBar("تم مسح تظليل البحث")

    def toggleComment(self):
        page = self.active_editor_page()
        if not page: return
        
        cursor = page.textEdit.textCursor()
        start_pos = cursor.selectionStart()
        end_pos = cursor.selectionEnd()
        doc = page.textEdit.document()

        cursor.beginEditBlock()

        start_block = doc.findBlock(start_pos)
        end_block = doc.findBlock(end_pos)

        if not cursor.hasSelection() or cursor.atBlockEnd():
             if start_pos != end_pos and doc.findBlock(end_pos).blockNumber() > start_block.blockNumber() and end_pos == doc.findBlock(end_pos).position():
                 end_block = end_block.previous()
        
        mode = 'comment'
        lines_to_process = []
        only_commented_lines_found = True
        has_code = False

        block = start_block
        while True:
            line_text = block.text()
            stripped_line = line_text.lstrip()
            lines_to_process.append(block)
            if stripped_line:
                 has_code = True
                 if not stripped_line.startswith('#'):
                      only_commented_lines_found = False
            if block == end_block:
                break
            block = block.next()
        
        if has_code and only_commented_lines_found:
             mode = 'uncomment'
        
        if mode == 'comment':
             min_indent = float('inf')
             for block in lines_to_process:
                  line_text = block.text()
                  stripped_line = line_text.lstrip()
                  if stripped_line:
                      indent = len(line_text) - len(stripped_line)
                      min_indent = min(min_indent, indent)
             if min_indent == float('inf'): min_indent = 0

             for block in lines_to_process:
                  mod_cursor = QTextCursor(block)
                  mod_cursor.setPosition(block.position() + min_indent)
                  mod_cursor.insertText("# ")

        elif mode == 'uncomment':
             for block in lines_to_process:
                  line_text = block.text()
                  stripped_line = line_text.lstrip()
                  if stripped_line.startswith('#'):
                      mod_cursor = QTextCursor(block)
                      indent = len(line_text) - len(stripped_line)
                      mod_cursor.setPosition(block.position() + indent)
                      if stripped_line.startswith('# '):
                          mod_cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 2)
                      else:
                          mod_cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 1)
                      mod_cursor.removeSelectedText()

        cursor.endEditBlock()
        page.textEdit.ensureCursorVisible()

    def analyzeImports(self):
        page = self.active_editor_page()
        if not page:
            self.updateStatusBar("لا يوجد لسان تبويب نشط لتحليله.")
            return

        code = page.textEdit.toPlainText()
        if not code.strip():
            QMessageBox.information(self, "📦 المكتبات المستوردة", "المحرر فارغ. لا توجد مكتبات لتحليلها.")
            return

        lines = code.splitlines()
        libraries = set()
        import_pattern = re.compile(r'^\s*(import|from)\s+([a-zA-Z0-9_\.]+)')

        for line in lines:
            stripped_line = line.strip()
            if not stripped_line or stripped_line.startswith('#'):
                continue

            match = import_pattern.match(line)
            if match:
                lib_path = match.group(2)
                if lib_path.startswith('.'):
                    continue
                base_lib = lib_path.split('.')[0]
                libraries.add(base_lib)

        if libraries:
            libs_list = sorted(libraries)
            libs_text = "\n".join(libs_list)
            
            reply = QMessageBox.question(
                self,
                "📦 المكتبات المستوردة",
                libs_text + "\n\nهل تريد نسخها إلى الحافظة بتنسيق 'pip install ...'؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                pip_command = f"pip install {' '.join(libs_list)}"
                clipboard = QApplication.clipboard()
                clipboard.setText(pip_command)
                QMessageBox.information(self, "✅ تم النسخ", "تم نسخ الأمر إلى الحافظة:\n" + pip_command)
                self.updateStatusBar("تم نسخ أمر تثبيت المكتبات إلى الحافظة.")
        else:
            QMessageBox.information(self, "📦 المكتبات المستوردة", "❌ لم يتم العثور على مكتبات.")
            self.updateStatusBar("لم يتم العثور على مكتبات في التحليل.")

    def runCode(self):
        page = self.active_editor_page()
        if not page:
            self.updateStatusBar("لا يوجد لسان تبويب نشط لتشغيل الكود.")
            return

        code = page.textEdit.toPlainText()
        if not code.strip():
            self.updateStatusBar("لا يوجد كود لتشغيله.")
            return

        if page.outputConsole.isHidden():
            self.handleOutputToggle(True)

        page.outputConsole.clear()
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        page.outputConsole.appendPlainText(f"--- بدأ التشغيل: {timestamp} ---")
        QApplication.processEvents()

        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8', errors='surrogateescape') as tf:
                tf.write(code)
                temp_file = tf.name
                script_dir = os.path.dirname(temp_file)

            self.updateStatusBar(f"جاري تشغيل {os.path.basename(temp_file)}...")
            QApplication.processEvents()

            startupinfo = None
            if sys.platform == "win32":
                 startupinfo = subprocess.STARTUPINFO()
                 startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                 startupinfo.wShowWindow = subprocess.SW_HIDE

            process = subprocess.run(
                [sys.executable or "python", os.path.basename(temp_file)],
                capture_output=True, text=True, encoding='utf-8',
                errors='replace', cwd=script_dir, timeout=30,
                startupinfo=startupinfo
            )

            if process.stdout:
                page.outputConsole.appendPlainText("\n--- الإخراج (stdout) ---")
                page.outputConsole.appendPlainText(process.stdout.strip())
            if process.stderr:
                page.outputConsole.appendPlainText("\n--- الأخطاء (stderr) ---")
                error_format = page.outputConsole.currentCharFormat()
                error_color = QColor("red") if self.is_dark_mode else QColor("darkred")
                if error_color.isValid():
                    error_format.setForeground(error_color)
                    cursor = page.outputConsole.textCursor()
                    cursor.movePosition(QTextCursor.MoveOperation.End)
                    cursor.insertText(process.stderr.strip(), error_format)
                    default_format = QTextCharFormat()
                    default_color = page.outputConsole.palette().color(QPalette.ColorRole.Text)
                    default_format.setForeground(default_color)
                    page.outputConsole.setCurrentCharFormat(default_format)
                else:
                     page.outputConsole.appendPlainText(process.stderr.strip())

            exit_code = process.returncode
            page.outputConsole.appendPlainText(f"\n--- انتهى (رمز الخروج: {exit_code}) ---")
            self.updateStatusBar(f"انتهى الكود (رمز الخروج: {exit_code}).")

        except subprocess.TimeoutExpired:
             page.outputConsole.appendPlainText("\n--- خطأ: انتهت مهلة التشغيل (30 ثانية)! ---")
             self.updateStatusBar("فشل تشغيل الكود: انتهت المهلة.")
        except FileNotFoundError:
             page.outputConsole.appendPlainText(f"\n--- خطأ: لم يتم العثور على مفسر بايثون ({sys.executable or 'python'}) ---")
             self.updateStatusBar("فشل تشغيل الكود: مفسر بايثون غير موجود.")
        except Exception as e:
            page.outputConsole.appendPlainText(f"\n--- خطأ في تشغيل المحرر للكود ---\n{type(e).__name__}: {e}")
            self.updateStatusBar(f"فشل تشغيل الكود: {type(e).__name__}")
        finally:
            if temp_file and os.path.exists(temp_file):
                try: os.remove(temp_file)
                except OSError as e: print(f"Warning: Could not delete temp file {temp_file}: {e}", file=sys.stderr)
            page.outputConsole.moveCursor(QTextCursor.MoveOperation.End)

    def showTextContextMenu(self, position: QPoint):
        page = self.active_editor_page()
        if not page: return

        menu = QMenu(self)
        cursor = page.textEdit.textCursor()

        can_undo = page.textEdit.document().isUndoAvailable()
        can_redo = page.textEdit.document().isRedoAvailable()
        has_selection = cursor.hasSelection()
        can_paste = page.textEdit.canPaste()
        has_content = not page.textEdit.document().isEmpty()

        undo_action = QAction("تراجع", self)
        undo_action.triggered.connect(page.textEdit.undo)
        undo_action.setEnabled(can_undo)
        menu.addAction(undo_action)

        redo_action = QAction("إعادة", self)
        redo_action.triggered.connect(page.textEdit.redo)
        redo_action.setEnabled(can_redo)
        menu.addAction(redo_action)

        menu.addSeparator()

        cut_action = QAction("قص", self)
        cut_action.triggered.connect(page.textEdit.cut)
        cut_action.setEnabled(has_selection)
        menu.addAction(cut_action)

        copy_action = QAction("نسخ", self)
        copy_action.triggered.connect(page.textEdit.copy)
        copy_action.setEnabled(has_selection)
        menu.addAction(copy_action)

        paste_action = QAction("لصق", self)
        paste_action.triggered.connect(page.textEdit.paste)
        paste_action.setEnabled(can_paste)
        menu.addAction(paste_action)

        select_all_action = QAction("تحديد الكل", self)
        select_all_action.triggered.connect(page.textEdit.selectAll)
        select_all_action.setEnabled(has_content)
        menu.addAction(select_all_action)

        menu.addSeparator()

        toggle_comment_action = QAction("تعليق السطر", self)
        toggle_comment_action.triggered.connect(self.toggleComment)
        menu.addAction(toggle_comment_action)

        menu.addSeparator()

        find_action = QAction("بحث", self)
        find_action.triggered.connect(self.toggleSearchBar)
        menu.addAction(find_action)

        run_action = QAction("تشغيل الكود", self)
        run_action.triggered.connect(self.runCode)
        menu.addAction(run_action)

        menu.exec(page.textEdit.viewport().mapToGlobal(position))

    def showOutputContextMenu(self, position: QPoint):
        page = self.active_editor_page()
        if not page: return

        menu = QMenu(self)
        cursor = page.outputConsole.textCursor()
        has_selection = cursor.hasSelection()
        has_content = not page.outputConsole.document().isEmpty()

        copy_action = QAction("نسخ", self)
        copy_action.triggered.connect(page.outputConsole.copy)
        copy_action.setEnabled(has_selection)
        menu.addAction(copy_action)

        select_all_action = QAction("تحديد الكل", self)
        select_all_action.triggered.connect(page.outputConsole.selectAll)
        select_all_action.setEnabled(has_content)
        menu.addAction(select_all_action)

        menu.addSeparator()

        clear_action = QAction("مسح الإخراج", self)
        clear_action.triggered.connect(page.outputConsole.clear)
        clear_action.setEnabled(has_content)
        menu.addAction(clear_action)

        menu.exec(page.outputConsole.viewport().mapToGlobal(position))

    def closeEvent(self, event):
        while self.tab_widget.count() > 0:
            if not self.close_tab_and_prompt(0):
                event.ignore()
                return
        event.accept()

    def close_tab_and_prompt(self, index):
        page = self.tab_widget.widget(index)
        if page.textEdit.document().isModified():
            self.tab_widget.setCurrentIndex(index)
            reply = QMessageBox.question(self, 'إغلاق المحرر',
                                         f"يوجد تغييرات لم يتم حفظها في الملف '{self.tab_widget.tabText(index).replace('*','')}'.\nهل تريد حفظها قبل الإغلاق؟",
                                         QMessageBox.StandardButton.Save |
                                         QMessageBox.StandardButton.Discard |
                                         QMessageBox.StandardButton.Cancel,
                                         QMessageBox.StandardButton.Save)

            if reply == QMessageBox.StandardButton.Save:
                if not self.saveFile():
                    return False
            elif reply == QMessageBox.StandardButton.Cancel:
                return False
        
        self.tab_widget.removeTab(index)
        return True


if __name__ == '__main__':
    app = QApplication(sys.argv)
    mainWin = AdvancedEditorTab()
    mainWin.show()
    sys.exit(app.exec())