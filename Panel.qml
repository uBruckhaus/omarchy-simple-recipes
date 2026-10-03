pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui as Ui

Ui.Panel {
    id: root
    moduleName: "ubruckhaus.simple-recipes"
    manageIpc: false
    property var anchorItem: null
    property var hostWidget: null
    property var info: ({})
    property var recipes: []
    property var labels: ({})
    property bool ready: false
    property bool favoritesOnly: false
    property bool checking: false
    property bool importStarting: false
    property string message: ""
    property string jobId: ""
    property int importedRecipe: 0
    property int searchGeneration: 0
    property int statusGeneration: 0
    readonly property var popupColors: Color.popups
    readonly property var styleFont: Style.font
    readonly property color foreground: popupColors.text
    readonly property bool targetVerified: (info.target_languages || []).some(function(row) { return row.code === info.target_language })
    readonly property bool importing: importStarting || jobId !== ""

    function tr(key) {
        var fallback = {title: "Simple Recipes", starting: "Starting recipe service…", unavailable: "Recipe service unavailable", retry: "Retry", search: "Search recipes or ingredients…", recent: "Recent recipes", favorites: "Favourites", empty: "No matching recipes", library: "Open recipe library", settings: "AI settings", import_link: "Paste a recipe link…", import: "Import", use_ai: "Translate with AI", working: "Importing recipe…", done: "Recipe imported", raw: "Saved without AI processing", failed: "Import failed. Check the link and try again.", languages: "Check languages", checking: "Checking model languages…", unverified: "No verified target languages yet", target: "Recipe language", layout: "Interface language", online: "Connected", offline: "Offline", configured: "Configured; connection not checked", open_recipe: "Open recipe", refresh: "Refresh"}
        return labels[key] || fallback[key] || key
    }
    function ensureVisible(item) {
        var position = item.mapToItem(content, 0, 0)
        if (position.y < body.contentY) body.contentY = position.y
        else if (position.y + item.height > body.contentY + body.height)
            body.contentY = Math.min(position.y + item.height - body.height, Math.max(0, body.contentHeight - body.height))
    }
    function request(method, path, body, done) {
        var xhr = new XMLHttpRequest()
        xhr.open(method, "http://127.0.0.1:8765" + path)
        xhr.setRequestHeader("Content-Type", "application/json")
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== XMLHttpRequest.DONE) return
            var data = {}
            try { data = JSON.parse(xhr.responseText) } catch (_) { /* Network errors have no JSON body. */ }
            done(xhr.status >= 200 && xhr.status < 300, data)
        }
        xhr.send(body === null ? null : JSON.stringify(body))
    }
    function open() {
        root.controller.show()
        root.message = ""
        if (!startup.running) startup.running = true
        if (root.jobId !== "") root.pollImport()
    }
    function close() { targetDropdown.close(); layoutDropdown.close(); root.controller.hide() }
    function toggle() { if (root.opened) root.close(); else root.open() }
    function refresh() {
        var version = ++root.statusGeneration
        request("GET", "/api/panel/status", null, function(ok, data) {
            if (version !== root.statusGeneration) return
            root.ready = ok
            if (!ok) { root.message = root.tr("unavailable"); return }
            root.info = data
            root.labels = data.labels || {}
            root.loadRecipes()
        })
    }
    function loadRecipes() {
        if (!root.ready) return
        var version = ++root.searchGeneration
        request("GET", "/api/panel/recipes?favorites=" + root.favoritesOnly + "&q=" + encodeURIComponent(search.text), null, function(ok, data) {
            if (version !== root.searchGeneration) return
            if (ok) root.recipes = data.recipes || []
            else root.message = root.tr("unavailable")
        })
    }
    function openLibrary(path) {
        Quickshell.execDetached(["bash", Qt.resolvedUrl("scripts/open.sh").toString().replace(/^file:\/\//, ""), path || "/"])
        root.close()
    }
    function setFavorite(recipe) {
        request("POST", "/api/panel/recipes/" + recipe.id + "/favorite", {favorite: !recipe.favorite}, function(ok) {
            if (ok) root.loadRecipes()
            else root.message = root.tr("unavailable")
        })
    }
    function checkLanguages() {
        root.checking = true
        var model = root.info.model
        var provider = root.info.provider
        request("POST", "/api/panel/languages", {}, function(ok, data) {
            root.checking = false
            if (root.info.model !== model || root.info.provider !== provider) return
            if (ok) root.refresh()
            else root.message = root.tr("unverified")
        })
    }
    function savePreference(values) {
        request("POST", "/api/panel/preferences", values, function(ok) {
            if (!ok) root.message = root.tr("unverified")
            root.refresh()
        })
    }
    function startImport() {
        if (root.importing || !link.text.trim()) return
        root.importStarting = true
        root.importedRecipe = 0
        root.message = root.tr("working")
        request("POST", "/api/panel/import", {url: link.text.trim(), use_ai: aiButton.selected && root.targetVerified}, function(ok, data) {
            root.importStarting = false
            if (!ok) { root.message = root.tr("failed"); return }
            root.jobId = data.id
            root.pollImport()
        })
    }
    function pollImport() {
        var id = root.jobId
        if (!id) return
        request("GET", "/api/panel/import/" + id, null, function(ok, data) {
            if (id !== root.jobId) return
            if (!ok || data.state === "failed") {
                root.jobId = ""
                root.message = root.tr("failed")
            } else if (data.state === "done") {
                root.jobId = ""
                root.importedRecipe = data.recipe_id || 0
                root.message = root.tr(data.without_ai ? "raw" : "done")
                link.text = ""
                root.refresh()
            }
        })
    }

    Process {
        id: startup
        command: ["bash", Qt.resolvedUrl("scripts/ensure-service.sh").toString().replace(/^file:\/\//, "")]
        onRunningChanged: { if (!running) root.refresh() }
    }
    Timer { id: searchDelay; interval: 250; onTriggered: root.loadRecipes() }
    Timer { interval: 2000; repeat: true; running: root.opened && root.jobId !== ""; onTriggered: root.pollImport() }

    Ui.KeyboardPanel {
        id: surface
        anchorItem: root.anchorItem
        owner: root.hostWidget || root
        bar: root.bar
        open: root.opened
        focusTarget: search
        contentWidth: surface.fittedContentWidth(Style.space(420))
        contentHeight: surface.fittedContentHeight(content.implicitHeight)

        Ui.PanelKeyCatcher {
            anchors.fill: parent
            // Let Qt's focus chain and text editors handle Tab/arrows naturally.
            blocked: true
            Keys.onEscapePressed: {
                if (targetDropdown.popupOpen) targetDropdown.close()
                else if (layoutDropdown.popupOpen) layoutDropdown.close()
                else root.close()
            }
            Flickable {
                id: body
                anchors.fill: parent
                contentHeight: content.implicitHeight
                contentWidth: width
                clip: true
                boundsBehavior: Flickable.StopAtBounds
            Column {
                id: content
                width: parent.width
                spacing: Style.space(8)
                Text {
                    width: parent.width
                    text: root.tr("title") + (root.ready ? " · " + root.info.recipe_count : "")
                    textFormat: Text.PlainText
                    font.family: root.styleFont.family
                    font.pixelSize: root.styleFont.subtitle
                    font.bold: true
                    color: root.foreground
                }
                Ui.TextField {
                    id: search
                    width: parent.width
                    enabled: root.ready
                    foreground: root.foreground
                    placeholderText: root.tr("search")
                    onActiveFocusChanged: { if (activeFocus) root.ensureVisible(search) }
                    onTextChanged: searchDelay.restart()
                    onAccepted: { if (root.recipes.length) root.openLibrary("/recipe/" + root.recipes[0].id) }
                }
                Flow {
                    width: parent.width
                    spacing: Style.space(6)
                    PanelButton {
                        panelRoot: root; text: root.tr("recent"); foreground: root.foreground; focusable: true; selected: !root.favoritesOnly; onClicked: { root.favoritesOnly = false; root.loadRecipes() } }
                    PanelButton {
                        panelRoot: root; text: "★ " + root.tr("favorites"); foreground: root.foreground; focusable: true; selected: root.favoritesOnly; onClicked: { root.favoritesOnly = true; root.loadRecipes() } }
                    Ui.PanelActionButton { iconText: "↻"; foreground: root.foreground; focusable: true; tooltipText: root.tr("refresh"); onClicked: root.refresh() }
                }
                ListView {
                    id: recipeList
                    width: parent.width
                    height: Math.min(Style.space(190), contentHeight)
                    clip: true
                    spacing: Style.space(4)
                    model: root.recipes
                    delegate: Row {
                        id: recipeRow
                        required property var modelData
                        required property int index
                        width: recipeList.width
                        spacing: Style.space(4)
                        PanelButton {
                        panelRoot: root;
                            width: parent.width - favoriteButton.width - parent.spacing
                            height: Style.space(36)
                            tooltipText: recipeRow.modelData.title + " · " + recipeRow.modelData.category + (recipeRow.modelData.duration_minutes ? " · " + recipeRow.modelData.duration_minutes + " min" : "")
                            leftAlign: true
                            foreground: root.foreground
                            focusable: true
                            onActiveFocusChanged: { if (activeFocus) recipeList.positionViewAtIndex(recipeRow.index, ListView.Contain) }
                            onClicked: root.openLibrary("/recipe/" + recipeRow.modelData.id)
                            Text {
                                anchors.fill: parent
                                anchors.margins: Style.space(6)
                                text: (recipeRow.modelData.emoji || "🍽️") + " " + recipeRow.modelData.title
                                textFormat: Text.PlainText
                                verticalAlignment: Text.AlignVCenter
                                elide: Text.ElideRight
                                color: root.foreground
                                font.family: root.styleFont.family
                                font.pixelSize: root.styleFont.body
                            }
                        }
                        Ui.PanelActionButton {
                            id: favoriteButton
                            iconText: recipeRow.modelData.favorite ? "★" : "☆"
                            tooltipText: root.tr("favorites")
                            foreground: root.foreground
                            focusable: true
                            onClicked: root.setFavorite(recipeRow.modelData)
                        }
                    }
                }
                Text {
                    visible: root.ready && root.recipes.length === 0
                    text: root.tr("empty")
                    textFormat: Text.PlainText
                    font.family: root.styleFont.family
                    font.pixelSize: root.styleFont.body
                    color: root.foreground
                }
                Text {
                    width: parent.width
                    text: root.ready ? root.info.provider_name + " · " + root.info.model + "\n" + root.tr(root.info.connected === true ? "online" : (root.info.connected === false ? "offline" : "configured")) : root.tr(startup.running ? "starting" : "unavailable")
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                    font.family: root.styleFont.family
                    font.pixelSize: root.styleFont.caption
                    color: root.foreground
                }
                Flow {
                    width: parent.width
                    spacing: Style.space(6)
                    PanelButton {
                        panelRoot: root; text: root.tr(root.checking ? "checking" : "languages"); foreground: root.foreground; focusable: true; enabled: root.ready && !root.checking; onClicked: root.checkLanguages() }
                    PanelButton {
                        panelRoot: root; text: root.tr("settings"); foreground: root.foreground; focusable: true; onClicked: root.openLibrary("/einstellungen") }
                }
                Row {
                    width: parent.width
                    spacing: Style.space(8)
                    Ui.Dropdown {
                        id: targetDropdown
                        width: (parent.width - parent.spacing) / 2
                        foreground: root.foreground
                        label: root.tr("target")
                        enabled: root.ready && !root.checking && (root.info.target_languages || []).length > 0
                        value: root.targetVerified ? root.info.target_language : ""
                        options: (root.info.target_languages || []).map(function(row) { return {value: row.code, label: row.name} })
                        onChanged: function(value) { root.savePreference({target_language: value}) }
                    }
                    Ui.Dropdown {
                        id: layoutDropdown
                        width: (parent.width - parent.spacing) / 2
                        foreground: root.foreground
                        label: root.tr("layout")
                        enabled: root.ready
                        value: root.info.ui_language || "en"
                        options: (root.info.layout_languages || []).map(function(row) { return {value: row.code, label: row.name} })
                        onChanged: function(value) { root.savePreference({ui_language: value}) }
                    }
                }
                Text {
                    visible: root.ready && !root.targetVerified && !root.checking
                    width: parent.width
                    text: root.tr("unverified")
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                    font.family: root.styleFont.family
                    font.pixelSize: root.styleFont.caption
                    color: root.foreground
                }
                Ui.TextField {
                    id: link
                    width: parent.width
                    foreground: root.foreground
                    enabled: root.ready && !root.importing
                    placeholderText: root.tr("import_link")
                    onActiveFocusChanged: { if (activeFocus) root.ensureVisible(link) }
                    onAccepted: root.startImport()
                }
                Flow {
                    width: parent.width
                    spacing: Style.space(6)
                    PanelButton {
                        panelRoot: root;
                        id: aiButton
                        text: (selected && root.targetVerified ? "✓ " : "") + root.tr("use_ai")
                        foreground: root.foreground
                        focusable: true
                        enabled: root.targetVerified && !root.checking && !root.importing
                        onClicked: selected = !selected
                    }
                    PanelButton {
                        panelRoot: root; text: root.tr(root.importing ? "working" : "import"); foreground: root.foreground; focusable: true; enabled: root.ready && !root.importing && link.text.trim() !== ""; onClicked: root.startImport() }
                }
                Text {
                    visible: root.message !== ""
                    width: parent.width
                    text: root.message
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                    font.family: root.styleFont.family
                    font.pixelSize: root.styleFont.caption
                    color: root.foreground
                }
                PanelButton {
                        panelRoot: root; visible: root.importedRecipe > 0; text: root.tr("open_recipe"); foreground: root.foreground; focusable: true; onClicked: root.openLibrary("/recipe/" + root.importedRecipe) }
                PanelButton {
                        panelRoot: root; visible: !root.ready && !startup.running; text: root.tr("retry"); foreground: root.foreground; focusable: true; onClicked: startup.running = true }
                PanelButton {
                        panelRoot: root; width: parent.width; text: root.tr("library"); foreground: root.foreground; focusable: true; bordered: true; onClicked: root.openLibrary("/") }
            }
            }
        }
    }
}
