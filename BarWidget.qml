pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import qs.Ui as Ui

Ui.BarWidget {
    id: root
    moduleName: "ubruckhaus.simple-recipes"
    function toggle() {
        Quickshell.execDetached(["bash", Qt.resolvedUrl("scripts/toggle.sh").toString().replace(/^file:\/\//, "")])
    }
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight
    Ui.BarIconButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        tooltipText: "Simple Recipes"
        iconComponent: Component {
            Canvas {
                id: cookbook
                property color ink: button.foreground
                onInkChanged: requestPaint()
                onWidthChanged: requestPaint()
                onHeightChanged: requestPaint()
                onPaint: {
                    var ctx = getContext("2d")
                    ctx.reset()
                    ctx.scale(width / 24, height / 24)
                    ctx.strokeStyle = ink
                    ctx.lineWidth = 1.8
                    ctx.lineCap = "round"
                    ctx.lineJoin = "round"
                    // Chef's toque: three rounded lobes and a folded band.
                    ctx.beginPath()
                    ctx.moveTo(6, 15)
                    ctx.bezierCurveTo(0, 14, 1, 5, 7, 6)
                    ctx.bezierCurveTo(7, 0, 17, 0, 17, 6)
                    ctx.bezierCurveTo(23, 5, 24, 14, 18, 15)
                    ctx.lineTo(18, 21)
                    ctx.lineTo(6, 21)
                    ctx.closePath()
                    ctx.moveTo(6, 17)
                    ctx.lineTo(18, 17)
                    ctx.stroke()
                }
            }
        }
        onPressed: function(buttonCode) {
            if (buttonCode === Qt.LeftButton) root.toggle()
            else if (buttonCode === Qt.RightButton)
                Quickshell.execDetached(["bash", Qt.resolvedUrl("scripts/open.sh").toString().replace(/^file:\/\//, "")])
        }
    }
}
