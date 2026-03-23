#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Markdown转Word文档工具
====================

将项目的Markdown文档转换为格式化的Word文档

依赖安装：
pip install python-docx markdown beautifulsoup4 lxml
"""

import os
import re
from pathlib import Path
from typing import List, Dict
import markdown
from bs4 import BeautifulSoup
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.shared import OxmlElement, qn

class MarkdownToWordConverter:
    """Markdown到Word转换器"""

    def __init__(self):
        self.doc = Document()
        self.setup_styles()

    def setup_styles(self):
        """设置文档样式"""
        # 设置默认字体
        self.doc.styles['Normal'].font.name = '微软雅黑'
        self.doc.styles['Normal'].font.size = Pt(11)

        # 标题样式
        for i in range(1, 4):
            heading_style = self.doc.styles[f'Heading {i}']
            heading_style.font.name = '微软雅黑'
            heading_style.font.bold = True
            if i == 1:
                heading_style.font.size = Pt(18)
                heading_style.font.color.rgb = RGBColor(0x1f, 0x4e, 0x79)
            elif i == 2:
                heading_style.font.size = Pt(16)
                heading_style.font.color.rgb = RGBColor(0x2e, 0x75, 0xb6)
            else:
                heading_style.font.size = Pt(14)
                heading_style.font.color.rgb = RGBColor(0x5b, 0x9b, 0xd5)

    def convert_markdown_to_word(self, md_file_path: str, output_path: str):
        """转换Markdown文件到Word"""
        print(f"转换文件: {md_file_path} -> {output_path}")

        # 读取Markdown文件
        with open(md_file_path, 'r', encoding='utf-8') as f:
            md_content = f.read()

        # 预处理Markdown内容
        md_content = self.preprocess_markdown(md_content)

        # 转换为HTML
        html = markdown.markdown(md_content, extensions=[
            'markdown.extensions.tables',
            'markdown.extensions.toc',
            'markdown.extensions.fenced_code'
        ])

        # 解析HTML
        soup = BeautifulSoup(html, 'html.parser')

        # 添加文档标题
        title = self.extract_title(md_content)
        if title:
            self.add_title_page(title)

        # 添加目录
        self.add_table_of_contents()

        # 转换HTML元素到Word
        self.convert_html_elements(soup)

        # 保存文档
        self.doc.save(output_path)
        print(f"✓ 转换完成: {output_path}")

    def preprocess_markdown(self, content: str) -> str:
        """预处理Markdown内容"""
        # 处理表格对齐
        content = re.sub(r'\|(\s*:-+\s*)\|', r'|\1|', content)

        # 处理代码块语言标识
        content = re.sub(r'```(\w+)', r'```\1', content)

        return content

    def extract_title(self, md_content: str) -> str:
        """提取文档标题"""
        lines = md_content.split('\n')
        for line in lines:
            if line.startswith('# '):
                return line[2:].strip()
        return ""

    def add_title_page(self, title: str):
        """添加标题页"""
        # 主标题
        title_paragraph = self.doc.add_paragraph()
        title_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        title_run = title_paragraph.add_run(title)
        title_run.font.size = Pt(24)
        title_run.font.bold = True
        title_run.font.color.rgb = RGBColor(0x1f, 0x4e, 0x79)

        # 空行
        self.doc.add_paragraph()

        # 副标题
        subtitle = self.doc.add_paragraph()
        subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
        subtitle_run = subtitle.add_run("技术文档")
        subtitle_run.font.size = Pt(16)
        subtitle_run.font.color.rgb = RGBColor(0x70, 0x70, 0x70)

        # 分页
        self.doc.add_page_break()

    def add_table_of_contents(self):
        """添加目录页"""
        # 目录标题
        toc_title = self.doc.add_paragraph()
        toc_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        toc_run = toc_title.add_run("目 录")
        toc_run.font.size = Pt(18)
        toc_run.font.bold = True

        # 目录说明
        toc_note = self.doc.add_paragraph()
        toc_note.alignment = WD_ALIGN_PARAGRAPH.CENTER
        toc_note_run = toc_note.add_run("（此处应插入自动生成的目录）")
        toc_note_run.font.size = Pt(10)
        toc_note_run.font.italic = True
        toc_note_run.font.color.rgb = RGBColor(0x70, 0x70, 0x70)

        # 分页
        self.doc.add_page_break()

    def convert_html_elements(self, soup: BeautifulSoup):
        """转换HTML元素到Word"""
        for element in soup.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'table', 'pre', 'ul', 'ol']):
            if element.name.startswith('h'):
                self.add_heading(element)
            elif element.name == 'p':
                self.add_paragraph(element)
            elif element.name == 'table':
                self.add_table(element)
            elif element.name == 'pre':
                self.add_code_block(element)
            elif element.name in ['ul', 'ol']:
                self.add_list(element)

    def add_heading(self, element):
        """添加标题"""
        level = int(element.name[1])
        text = element.get_text().strip()

        if level <= 3:
            heading = self.doc.add_heading(text, level=level)
        else:
            # 四级标题用加粗段落
            para = self.doc.add_paragraph()
            run = para.add_run(text)
            run.font.bold = True
            run.font.size = Pt(12)

    def add_paragraph(self, element):
        """添加段落"""
        text = element.get_text().strip()
        if text:
            para = self.doc.add_paragraph(text)

            # 处理特殊格式
            if text.startswith('> '):
                # 引用块
                para.style = 'Quote'
            elif '⚠️' in text or '🔴' in text:
                # 警告文本
                para.runs[0].font.color.rgb = RGBColor(0xff, 0x00, 0x00)

    def add_table(self, element):
        """添加表格"""
        rows = element.find_all('tr')
        if not rows:
            return

        # 创建表格
        cols = len(rows[0].find_all(['th', 'td']))
        table = self.doc.add_table(rows=len(rows), cols=cols)
        table.style = 'Table Grid'
        table.alignment = WD_TABLE_ALIGNMENT.CENTER

        # 填充表格数据
        for i, row in enumerate(rows):
            cells = row.find_all(['th', 'td'])
            for j, cell in enumerate(cells):
                if i < len(table.rows) and j < len(table.rows[i].cells):
                    table_cell = table.rows[i].cells[j]
                    table_cell.text = cell.get_text().strip()

                    # 表头格式
                    if cell.name == 'th':
                        for paragraph in table_cell.paragraphs:
                            for run in paragraph.runs:
                                run.font.bold = True

    def add_code_block(self, element):
        """添加代码块"""
        code_text = element.get_text().strip()
        if code_text:
            para = self.doc.add_paragraph()
            run = para.add_run(code_text)
            run.font.name = 'Consolas'
            run.font.size = Pt(9)

            # 设置背景色
            para.style = 'No Spacing'

    def add_list(self, element):
        """添加列表"""
        list_items = element.find_all('li')
        for item in list_items:
            text = item.get_text().strip()
            if text:
                if element.name == 'ul':
                    # 无序列表
                    para = self.doc.add_paragraph(text, style='List Bullet')
                else:
                    # 有序列表
                    para = self.doc.add_paragraph(text, style='List Number')

def main():
    """主函数"""
    print("=" * 50)
    print("Markdown转Word文档转换器")
    print("=" * 50)

    converter = MarkdownToWordConverter()

    # 转换文件列表
    conversions = [
        {
            'input': 'docs/迁移方案详细文档.md',
            'output': 'docs/翻车机积煤检测系统V3.0-迁移方案.docx'
        },
        {
            'input': 'docs/系统架构设计文档.md',
            'output': 'docs/翻车机积煤检测系统V3.0-架构设计.docx'
        }
    ]

    # 执行转换
    for conversion in conversions:
        try:
            if os.path.exists(conversion['input']):
                converter = MarkdownToWordConverter()  # 每个文档创建新的转换器
                converter.convert_markdown_to_word(
                    conversion['input'],
                    conversion['output']
                )
            else:
                print(f"✗ 文件不存在: {conversion['input']}")
        except Exception as e:
            print(f"✗ 转换失败 {conversion['input']}: {e}")

    print("\n" + "=" * 50)
    print("转换完成！")
    print("=" * 50)

if __name__ == "__main__":
    main()