#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyQt6应用程序样式定义
提供现代化、专业的界面外观
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette, QColor, QFont
from PyQt6.QtWidgets import QApplication


class ModernStyle:
    """现代化样式类"""
    
    # 颜色定义
    COLORS = {
        # 主色调
        'primary': '#3498db',
        'primary_dark': '#2980b9',
        'primary_light': '#5dade2',
        
        # 辅助色
        'secondary': '#2c3e50',
        'secondary_light': '#34495e',
        
        # 状态色
        'success': '#27ae60',
        'warning': '#f39c12',
        'danger': '#e74c3c',
        'info': '#17a2b8',
        
        # 中性色
        'light': '#f8f9fa',
        'dark': '#343a40',
        'white': '#ffffff',
        'gray_100': '#f8f9fa',
        'gray_200': '#e9ecef',
        'gray_300': '#dee2e6',
        'gray_400': '#ced4da',
        'gray_500': '#adb5bd',
        'gray_600': '#6c757d',
        'gray_700': '#495057',
        'gray_800': '#343a40',
        'gray_900': '#212529',
        
        # 背景色
        'bg_primary': '#ffffff',
        'bg_secondary': '#f8f9fa',
        'bg_tertiary': '#e9ecef',
        
        # 文本色
        'text_primary': '#212529',
        'text_secondary': '#6c757d',
        'text_light': '#ffffff',
    }
    
    @classmethod
    def get_main_stylesheet(cls):
        """获取主样式表"""
        return f"""
        /* 全局样式 */
        QMainWindow {{
            background: {cls.COLORS['bg_primary']};
            color: {cls.COLORS['text_primary']};
            font-family: 'Segoe UI', 'Arial', sans-serif;
            font-size: 14px;
        }}
        
        /* 菜单栏样式 */
        QMenuBar {{
            background: {cls.COLORS['bg_secondary']};
            border-bottom: 1px solid {cls.COLORS['gray_300']};
            padding: 4px;
        }}
        
        QMenuBar::item {{
            background: transparent;
            padding: 8px 12px;
            border-radius: 4px;
            margin: 2px;
        }}
        
        QMenuBar::item:selected {{
            background: {cls.COLORS['primary_light']};
            color: {cls.COLORS['text_light']};
        }}
        
        QMenu {{
            background: {cls.COLORS['white']};
            border: 1px solid {cls.COLORS['gray_300']};
            border-radius: 6px;
            padding: 4px;
        }}
        
        QMenu::item {{
            padding: 8px 24px;
            border-radius: 4px;
        }}
        
        QMenu::item:selected {{
            background: {cls.COLORS['primary_light']};
            color: {cls.COLORS['text_light']};
        }}
        
        /* 工具栏样式 */
        QToolBar {{
            background: {cls.COLORS['bg_secondary']};
            border: none;
            spacing: 4px;
            padding: 6px;
        }}
        
        QToolBar::separator {{
            background: {cls.COLORS['gray_300']};
            width: 1px;
            margin: 4px 8px;
        }}
        
        /* 状态栏样式 */
        QStatusBar {{
            background: {cls.COLORS['bg_secondary']};
            border-top: 1px solid {cls.COLORS['gray_300']};
            padding: 4px;
        }}
        
        /* 分组框样式 */
        QGroupBox {{
            font-weight: bold;
            border: 2px solid {cls.COLORS['gray_300']};
            border-radius: 8px;
            margin-top: 12px;
            padding-top: 8px;
            background: {cls.COLORS['white']};
        }}
        
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 8px 0 8px;
            color: {cls.COLORS['secondary']};
            background: {cls.COLORS['white']};
        }}
        
        /* 标签页样式 */
        QTabWidget::pane {{
            border: 1px solid {cls.COLORS['gray_300']};
            border-radius: 6px;
            background: {cls.COLORS['white']};
        }}
        
        QTabBar::tab {{
            background: {cls.COLORS['gray_200']};
            padding: 12px 20px;
            margin-right: 2px;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            min-width: 100px;
        }}
        
        QTabBar::tab:selected {{
            background: {cls.COLORS['primary']};
            color: {cls.COLORS['text_light']};
        }}
        
        QTabBar::tab:hover:!selected {{
            background: {cls.COLORS['primary_light']};
            color: {cls.COLORS['text_light']};
        }}
        
        /* 按钮基础样式 */
        QPushButton {{
            background: {cls.COLORS['primary']};
            color: {cls.COLORS['text_light']};
            border: none;
            border-radius: 6px;
            padding: 10px 20px;
            font-weight: bold;
            font-size: 14px;
            min-height: 20px;
        }}
        
        QPushButton:hover {{
            background: {cls.COLORS['primary_dark']};
        }}
        
        QPushButton:pressed {{
            background: {cls.COLORS['primary_dark']};
            padding-top: 11px;
            padding-bottom: 9px;
        }}
        
        QPushButton:disabled {{
            background: {cls.COLORS['gray_400']};
            color: {cls.COLORS['gray_600']};
        }}
        
        /* 输入框样式 */
        QLineEdit, QTextEdit, QPlainTextEdit {{
            border: 2px solid {cls.COLORS['gray_300']};
            border-radius: 6px;
            padding: 8px 12px;
            background: {cls.COLORS['white']};
            selection-background-color: {cls.COLORS['primary_light']};
        }}
        
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
            border-color: {cls.COLORS['primary']};
        }}
        
        /* 下拉框样式 */
        QComboBox {{
            border: 2px solid {cls.COLORS['gray_300']};
            border-radius: 6px;
            padding: 8px 12px;
            background: {cls.COLORS['white']};
            min-width: 80px;
        }}
        
        QComboBox:focus {{
            border-color: {cls.COLORS['primary']};
        }}
        
        QComboBox::drop-down {{
            border: none;
            width: 20px;
        }}
        
        QComboBox::down-arrow {{
            image: url(down_arrow.png);
            width: 12px;
            height: 12px;
        }}
        
        QComboBox QAbstractItemView {{
            border: 1px solid {cls.COLORS['gray_300']};
            border-radius: 6px;
            background: {cls.COLORS['white']};
            selection-background-color: {cls.COLORS['primary_light']};
        }}
        
        /* 数值输入框样式 */
        QSpinBox, QDoubleSpinBox {{
            border: 2px solid {cls.COLORS['gray_300']};
            border-radius: 6px;
            padding: 8px 12px;
            background: {cls.COLORS['white']};
        }}
        
        QSpinBox:focus, QDoubleSpinBox:focus {{
            border-color: {cls.COLORS['primary']};
        }}
        
        /* 滑块样式 */
        QSlider::groove:horizontal {{
            border: 1px solid {cls.COLORS['gray_400']};
            height: 6px;
            background: {cls.COLORS['gray_200']};
            border-radius: 3px;
        }}
        
        QSlider::handle:horizontal {{
            background: {cls.COLORS['primary']};
            border: 2px solid {cls.COLORS['primary_dark']};
            width: 20px;
            margin: -8px 0;
            border-radius: 10px;
        }}
        
        QSlider::handle:horizontal:hover {{
            background: {cls.COLORS['primary_light']};
        }}
        
        /* 进度条样式 */
        QProgressBar {{
            border: 2px solid {cls.COLORS['gray_300']};
            border-radius: 8px;
            text-align: center;
            font-weight: bold;
            background: {cls.COLORS['gray_200']};
            color: {cls.COLORS['text_primary']};
        }}
        
        QProgressBar::chunk {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {cls.COLORS['primary']}, 
                stop:0.5 {cls.COLORS['primary_light']}, 
                stop:1 {cls.COLORS['primary']});
            border-radius: 6px;
        }}
        
        /* 复选框样式 */
        QCheckBox {{
            spacing: 8px;
        }}
        
        QCheckBox::indicator {{
            width: 20px;
            height: 20px;
            border: 2px solid {cls.COLORS['gray_400']};
            border-radius: 4px;
            background: {cls.COLORS['white']};
        }}
        
        QCheckBox::indicator:checked {{
            background: {cls.COLORS['primary']};
            border-color: {cls.COLORS['primary_dark']};
        }}
        
        QCheckBox::indicator:checked::before {{
            content: "✓";
            color: {cls.COLORS['text_light']};
            font-weight: bold;
        }}
        
        /* 表格样式 */
        QTableWidget {{
            gridline-color: {cls.COLORS['gray_300']};
            background: {cls.COLORS['white']};
            alternate-background-color: {cls.COLORS['gray_100']};
            selection-background-color: {cls.COLORS['primary_light']};
            border: 1px solid {cls.COLORS['gray_300']};
            border-radius: 6px;
        }}
        
        QTableWidget::item {{
            padding: 8px;
        }}
        
        QHeaderView::section {{
            background: {cls.COLORS['gray_200']};
            padding: 8px;
            border: none;
            border-right: 1px solid {cls.COLORS['gray_300']};
            border-bottom: 1px solid {cls.COLORS['gray_300']};
            font-weight: bold;
        }}
        
        /* 滚动条样式 */
        QScrollBar:vertical {{
            border: none;
            background: {cls.COLORS['gray_200']};
            width: 12px;
            border-radius: 6px;
        }}
        
        QScrollBar::handle:vertical {{
            background: {cls.COLORS['gray_400']};
            border-radius: 6px;
            min-height: 20px;
        }}
        
        QScrollBar::handle:vertical:hover {{
            background: {cls.COLORS['gray_500']};
        }}
        
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            border: none;
            background: none;
        }}
        
        /* 对话框样式 */
        QDialog {{
            background: {cls.COLORS['white']};
            border-radius: 8px;
        }}
        
        QDialogButtonBox QPushButton {{
            min-width: 80px;
        }}
        
        /* 框架样式 */
        QFrame {{
            border-radius: 6px;
        }}
        
        /* 分割器样式 */
        QSplitter::handle {{
            background: {cls.COLORS['gray_300']};
        }}
        
        QSplitter::handle:horizontal {{
            width: 2px;
        }}
        
        QSplitter::handle:vertical {{
            height: 2px;
        }}
        """
    
    @classmethod
    def get_button_style(cls, button_type='primary'):
        """获取特定类型按钮样式"""
        styles = {
            'primary': f"""
                QPushButton {{
                    background: {cls.COLORS['primary']};
                    color: {cls.COLORS['text_light']};
                }}
                QPushButton:hover {{
                    background: {cls.COLORS['primary_dark']};
                }}
            """,
            
            'success': f"""
                QPushButton {{
                    background: {cls.COLORS['success']};
                    color: {cls.COLORS['text_light']};
                }}
                QPushButton:hover {{
                    background: #229954;
                }}
            """,
            
            'warning': f"""
                QPushButton {{
                    background: {cls.COLORS['warning']};
                    color: {cls.COLORS['text_light']};
                }}
                QPushButton:hover {{
                    background: #e67e22;
                }}
            """,
            
            'danger': f"""
                QPushButton {{
                    background: {cls.COLORS['danger']};
                    color: {cls.COLORS['text_light']};
                }}
                QPushButton:hover {{
                    background: #c0392b;
                }}
            """,
            
            'secondary': f"""
                QPushButton {{
                    background: {cls.COLORS['gray_500']};
                    color: {cls.COLORS['text_light']};
                }}
                QPushButton:hover {{
                    background: {cls.COLORS['gray_600']};
                }}
            """
        }
        return styles.get(button_type, styles['primary'])
    
    @classmethod
    def get_card_style(cls):
        """获取卡片样式"""
        return f"""
            QFrame {{
                background: {cls.COLORS['white']};
                border: 1px solid {cls.COLORS['gray_300']};
                border-radius: 12px;
                padding: 16px;
            }}
            
            QFrame:hover {{
                border-color: {cls.COLORS['primary']};
                box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            }}
        """
    
    @classmethod
    def get_metric_card_style(cls):
        """获取指标卡片样式"""
        return f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {cls.COLORS['white']}, 
                    stop:1 {cls.COLORS['gray_100']});
                border: 1px solid {cls.COLORS['gray_300']};
                border-radius: 12px;
                padding: 20px;
                min-height: 120px;
            }}
            
            QFrame:hover {{
                border: 2px solid {cls.COLORS['primary']};
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {cls.COLORS['gray_100']}, 
                    stop:1 {cls.COLORS['gray_200']});
            }}
        """
    
    @classmethod
    def get_dark_theme_palette(cls):
        """获取深色主题调色板"""
        dark_palette = QPalette()
        
        # 窗口颜色
        dark_palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
        
        # 基础颜色
        dark_palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
        dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
        
        # 提示颜色
        dark_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(0, 0, 0))
        dark_palette.setColor(QPalette.ColorRole.ToolTipText, QColor(255, 255, 255))
        
        # 文本颜色
        dark_palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
        
        # 按钮颜色
        dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
        
        # 高亮颜色
        dark_palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
        dark_palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))
        
        return dark_palette
    
    @classmethod
    def apply_theme(cls, app, theme='light'):
        """应用主题"""
        if theme == 'dark':
            app.setPalette(cls.get_dark_theme_palette())
        
        # 设置字体
        font = QFont("Segoe UI", 10)
        app.setFont(font)
        
        # 应用样式表
        app.setStyleSheet(cls.get_main_stylesheet())


class AnimationStyles:
    """动画样式类"""
    
    @staticmethod
    def get_fade_in_style():
        """淡入动画样式"""
        return """
            QWidget {
                animation: fadeIn 0.3s ease-in-out;
            }
            
            @keyframes fadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }
        """
    
    @staticmethod
    def get_slide_in_style():
        """滑入动画样式"""
        return """
            QWidget {
                animation: slideIn 0.4s ease-out;
            }
            
            @keyframes slideIn {
                from { transform: translateX(-100%); }
                to { transform: translateX(0); }
            }
        """
    
    @staticmethod
    def get_bounce_style():
        """弹跳动画样式"""
        return """
            QWidget {
                animation: bounce 0.6s ease;
            }
            
            @keyframes bounce {
                0%, 20%, 50%, 80%, 100% {
                    transform: translateY(0);
                }
                40% {
                    transform: translateY(-10px);
                }
                60% {
                    transform: translateY(-5px);
                }
            }
        """


class IconStyles:
    """图标样式类"""
    
    # 常用图标Unicode
    ICONS = {
        'play': '▶️',
        'pause': '⏸️',
        'stop': '⏹️',
        'settings': '⚙️',
        'save': '💾',
        'load': '📁',
        'export': '📤',
        'import': '📥',
        'chart': '📊',
        'map': '🗺️',
        'user': '👤',
        'car': '🚗',
        'battery': '🔋',
        'lightning': '⚡',
        'warning': '⚠️',
        'success': '✅',
        'error': '❌',
        'info': 'ℹ️',
        'refresh': '🔄',
        'search': '🔍',
        'filter': '🔽',
        'sort': '↕️',
        'up': '↑',
        'down': '↓',
        'left': '←',
        'right': '→'
    }
    
    @classmethod
    def get_icon_button_style(cls, icon_name):
        """获取图标按钮样式"""
        icon = cls.ICONS.get(icon_name, '●')
        return f"""
            QPushButton {{
                text-align: center;
                font-size: 16px;
                min-width: 40px;
                min-height: 40px;
                border-radius: 20px;
            }}
            
            QPushButton::before {{
                content: "{icon}";
            }}
        """


def apply_modern_style(app):
    """应用现代化样式到应用程序"""
    ModernStyle.apply_theme(app, 'light')
    
    # 设置应用程序属性
    app.setStyle('Fusion')  # 使用Fusion样式作为基础
    
    return True


# 导出样式类
__all__ = [
    'ModernStyle',
    'AnimationStyles', 
    'IconStyles',
    'apply_modern_style'
]
