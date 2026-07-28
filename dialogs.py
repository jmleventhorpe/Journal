"""Password dialogs shown before the main journal window ever appears."""

from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton


class SetPasswordDialog(QDialog):
    """Shown once, the very first time the journal is created."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Create your journal password")
        self.setMinimumWidth(380)
        self.password = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "This password encrypts your journal.\n"
            "There is no recovery - if you lose it, your entries cannot be read again."
        ))

        self.pw1 = QLineEdit()
        self.pw1.setEchoMode(QLineEdit.Password)
        self.pw1.setPlaceholderText("Password")
        layout.addWidget(self.pw1)

        self.pw2 = QLineEdit()
        self.pw2.setEchoMode(QLineEdit.Password)
        self.pw2.setPlaceholderText("Confirm password")
        layout.addWidget(self.pw2)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #f48771;")
        layout.addWidget(self.error_label)

        btn = QPushButton("Create Journal")
        btn.clicked.connect(self._submit)
        layout.addWidget(btn)

    def _submit(self):
        p1, p2 = self.pw1.text(), self.pw2.text()
        if len(p1) < 4:
            self.error_label.setText("Password must be at least 4 characters.")
            return
        if p1 != p2:
            self.error_label.setText("Passwords don't match.")
            return
        self.password = p1
        self.accept()


class UnlockDialog(QDialog):
    """Shown every launch after the journal already exists."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Unlock journal")
        self.setMinimumWidth(320)
        self.password = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Enter your journal password:"))

        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.Password)
        self.pw.returnPressed.connect(self._submit)
        layout.addWidget(self.pw)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #f48771;")
        layout.addWidget(self.error_label)

        btn = QPushButton("Unlock")
        btn.clicked.connect(self._submit)
        layout.addWidget(btn)

        self.pw.setFocus()

    def _submit(self):
        self.password = self.pw.text()
        self.accept()

    def show_error(self, msg):
        self.error_label.setText(msg)
        self.pw.clear()
        self.pw.setFocus()
