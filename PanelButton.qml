import QtQuick
import qs.Ui as Ui

Ui.Button {
    id: control
    property var panelRoot: null
    clip: true
    focusable: true
    onActiveFocusChanged: {
        if (activeFocus && panelRoot) panelRoot.ensureVisible(control)
    }
}
