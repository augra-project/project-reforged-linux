# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""Checks on Qt widgets that more than one test module needs."""

from PySide6.QtGui import QFont, QFontInfo, QPalette
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton

from project_reforged_linux.ui import theme


def text_colour(label: QLabel) -> str:
    return label.palette().color(QPalette.ColorRole.WindowText).name()


def check_night(dialog: QDialog, fonts: theme.Fonts) -> None:
    # Pale text on Qt's light box, the launcher's big
    # button font on the dialog's buttons. Measured on the children, where it went wrong.
    dialog.show()
    QApplication.processEvents()
    assert dialog.palette().color(QPalette.ColorRole.Window).name() == theme.PLUM
    labels = [label for label in dialog.findChildren(QLabel) if label.text()]
    assert labels and all(text_colour(label) == theme.TEXT for label in labels)
    buttons = dialog.findChildren(QPushButton)
    assert buttons
    for button in buttons:
        assert QFontInfo(button.font()).family() == fonts.text, button.text()
        assert button.font().pointSize() == theme.BASE_PT
        assert button.font().weight() < QFont.Weight.DemiBold
    dialog.hide()
