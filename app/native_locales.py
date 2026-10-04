KEYS = ["library", "import_tab", "settings", "help", "new", "edit", "save", "cancel", "delete", "close", "backup", "export", "restore", "all", "add_category", "rename_category", "delete_category", "setup", "setup_intro", "no_ai", "codex", "local", "finish", "select_check", "checking", "working", "saved", "failed", "duplicate", "reset", "confirm_delete", "confirm_reset", "target_hint", "copy", "source", "image", "video_search", "search", "timer", "timer_done", "import_done", "raw", "model_ready", "model_missing", "backup_done", "restore_done", "done", "minutes", "next", "previous", "privacy", "rename", "welcome", "setup_help"]
TEXT = {
    "en": dict(zip(KEYS, ["Recipe library", "Import", "Settings", "Help", "New recipe", "Edit", "Save", "Cancel", "Delete", "Close", "Back up database", "Export recipes", "Restore recipes", "All categories", "Add category", "Rename category", "Delete category", "First-run setup", "Choose your interface language and optional AI. You can import recipes without AI and configure a model later.", "Use without AI", "Codex — existing ChatGPT login", "Local llama.cpp server", "Finish setup", "Select model and check languages", "Checking model and languages…", "Working… You can hide this window; processing continues.", "Saved", "The request failed. Check the recipe link, model or login and retry.", "This recipe is already in your library.", "Reset recipes and settings", "Delete this recipe permanently?", "Delete all recipes, categories, the phone number, API keys and preferences? This cannot be undone.", "Select a model and check its languages before choosing a target or enabling AI.", "Copy recipe", "Open original recipe", "Open recipe image", "Search YouTube", "Search", "Timer", "Timer finished", "Recipe imported", "Recipe saved without AI processing", "Model selected", "Choose a model", "Backup saved", "Recipes restored", "Done", "minutes", "Next", "Previous", "Online AI receives the recipe text and uses your account limits. Codex owns its login; the app never copies it. Other API keys are stored in your private database.", "Rename", "Welcome to Simple Recipes", "Setup checks your selected AI and lists verified target languages. You can use the recipe library immediately without AI."])),
    "de": dict(zip(KEYS, ["Rezeptsammlung", "Importieren", "Einstellungen", "Hilfe", "Neues Rezept", "Bearbeiten", "Speichern", "Abbrechen", "Löschen", "Schließen", "Datenbank sichern", "Rezepte exportieren", "Rezepte wiederherstellen", "Alle Kategorien", "Kategorie hinzufügen", "Kategorie umbenennen", "Kategorie löschen", "Ersteinrichtung", "Wählen Sie die Oberflächensprache und optional eine KI. Rezepte können ohne KI importiert werden; ein Modell lässt sich später einrichten.", "Ohne KI verwenden", "Codex — vorhandene ChatGPT-Anmeldung", "Lokaler llama.cpp-Server", "Einrichtung abschließen", "Modell wählen und Sprachen prüfen", "Modell und Sprachen werden geprüft…", "Verarbeitung läuft… Sie können dieses Fenster ausblenden; die Verarbeitung läuft weiter.", "Gespeichert", "Anfrage fehlgeschlagen. Rezeptlink, Modell oder Anmeldung prüfen und erneut versuchen.", "Dieses Rezept ist bereits in Ihrer Sammlung.", "Rezepte und Einstellungen zurücksetzen", "Dieses Rezept dauerhaft löschen?", "Alle Rezepte, Kategorien, die Telefonnummer, API-Schlüssel und Einstellungen löschen? Dies kann nicht rückgängig gemacht werden.", "Ein Modell wählen und seine Sprachen prüfen, bevor Sie eine Zielsprache oder KI aktivieren.", "Rezept kopieren", "Originalrezept öffnen", "Rezeptbild öffnen", "YouTube durchsuchen", "Suchen", "Timer", "Timer abgelaufen", "Rezept importiert", "Rezept ohne KI-Verarbeitung gespeichert", "Modell ausgewählt", "Modell auswählen", "Sicherung gespeichert", "Rezepte wiederhergestellt", "Fertig", "Minuten", "Weiter", "Zurück", "Online-KI erhält den Rezepttext und nutzt Ihre Kontingente. Codex verwaltet seine Anmeldung selbst. Andere API-Schlüssel liegen in Ihrer privaten Datenbank.", "Umbenennen", "Willkommen bei Simple Recipes", "Die Einrichtung prüft Ihre KI und zeigt geprüfte Zielsprachen. Die Rezeptsammlung ist sofort ohne KI nutzbar."])),
    "fr": dict(zip(KEYS, ["Collection de recettes", "Importer", "Paramètres", "Aide", "Nouvelle recette", "Modifier", "Enregistrer", "Annuler", "Supprimer", "Fermer", "Sauvegarder la base", "Exporter les recettes", "Restaurer les recettes", "Toutes les catégories", "Ajouter une catégorie", "Renommer une catégorie", "Supprimer une catégorie", "Configuration initiale", "Choisissez la langue de l’interface et une IA facultative. Vous pouvez importer sans IA et configurer un modèle plus tard.", "Utiliser sans IA", "Codex — connexion ChatGPT existante", "Serveur llama.cpp local", "Terminer la configuration", "Choisir le modèle et vérifier les langues", "Vérification du modèle et des langues…", "Traitement en cours… Vous pouvez masquer cette fenêtre.", "Enregistré", "Échec de la demande. Vérifiez le lien, le modèle ou la connexion et réessayez.", "Cette recette est déjà dans votre collection.", "Réinitialiser les recettes et paramètres", "Supprimer définitivement cette recette ?", "Supprimer toutes les recettes, catégories, le téléphone, les clés API et préférences ? Cette action est irréversible.", "Choisissez un modèle et vérifiez ses langues avant d’activer l’IA.", "Copier la recette", "Ouvrir la recette originale", "Ouvrir l’image", "Rechercher sur YouTube", "Rechercher", "Minuteur", "Minuteur terminé", "Recette importée", "Recette enregistrée sans IA", "Modèle sélectionné", "Choisir un modèle", "Sauvegarde enregistrée", "Recettes restaurées", "Terminé", "minutes", "Suivant", "Précédent", "L’IA en ligne reçoit le texte et utilise votre quota. Codex gère sa connexion ; les autres clés API sont stockées dans votre base privée.", "Renommer", "Bienvenue dans Simple Recipes", "La configuration vérifie l’IA et affiche les langues vérifiées. La collection fonctionne immédiatement sans IA."])),
    "it": dict(zip(KEYS, ["Raccolta di ricette", "Importa", "Impostazioni", "Aiuto", "Nuova ricetta", "Modifica", "Salva", "Annulla", "Elimina", "Chiudi", "Salva copia del database", "Esporta ricette", "Ripristina ricette", "Tutte le categorie", "Aggiungi categoria", "Rinomina categoria", "Elimina categoria", "Configurazione iniziale", "Scegli la lingua e un’IA facoltativa. Puoi importare senza IA e configurare un modello in seguito.", "Usa senza IA", "Codex — accesso ChatGPT esistente", "Server llama.cpp locale", "Completa configurazione", "Scegli modello e verifica lingue", "Verifica del modello e delle lingue…", "Elaborazione in corso… Puoi nascondere questa finestra.", "Salvato", "Richiesta non riuscita. Controlla link, modello o accesso e riprova.", "Questa ricetta è già nella raccolta.", "Reimposta ricette e impostazioni", "Eliminare definitivamente questa ricetta?", "Eliminare tutte le ricette, categorie, telefono, chiavi API e preferenze? L’operazione è irreversibile.", "Scegli un modello e verifica le lingue prima di attivare l’IA.", "Copia ricetta", "Apri ricetta originale", "Apri immagine", "Cerca su YouTube", "Cerca", "Timer", "Timer terminato", "Ricetta importata", "Ricetta salvata senza IA", "Modello selezionato", "Scegli un modello", "Copia salvata", "Ricette ripristinate", "Fine", "minuti", "Avanti", "Indietro", "L’IA online riceve il testo e usa la quota del tuo account. Codex gestisce l’accesso; le altre chiavi API sono nel database privato.", "Rinomina", "Benvenuto in Simple Recipes", "La configurazione verifica l’IA e mostra le lingue disponibili. La raccolta funziona subito senza IA."])),
    "es": dict(zip(KEYS, ["Colección de recetas", "Importar", "Ajustes", "Ayuda", "Nueva receta", "Editar", "Guardar", "Cancelar", "Eliminar", "Cerrar", "Guardar copia de la base", "Exportar recetas", "Restaurar recetas", "Todas las categorías", "Añadir categoría", "Renombrar categoría", "Eliminar categoría", "Configuración inicial", "Elige el idioma y una IA opcional. Puedes importar sin IA y configurar un modelo después.", "Usar sin IA", "Codex — sesión ChatGPT existente", "Servidor llama.cpp local", "Completar configuración", "Elegir modelo y comprobar idiomas", "Comprobando modelo e idiomas…", "Procesando… Puedes ocultar esta ventana.", "Guardado", "Error en la solicitud. Comprueba el enlace, modelo o sesión y reintenta.", "Esta receta ya está en tu colección.", "Restablecer recetas y ajustes", "¿Eliminar esta receta permanentemente?", "¿Eliminar todas las recetas, categorías, teléfono, claves API y preferencias? Esta acción es irreversible.", "Elige un modelo y comprueba sus idiomas antes de activar la IA.", "Copiar receta", "Abrir receta original", "Abrir imagen", "Buscar en YouTube", "Buscar", "Temporizador", "Temporizador terminado", "Receta importada", "Receta guardada sin IA", "Modelo seleccionado", "Elegir modelo", "Copia guardada", "Recetas restauradas", "Listo", "minutos", "Siguiente", "Anterior", "La IA online recibe el texto y usa tu cuota. Codex gestiona su sesión; las otras claves API se guardan en la base privada.", "Renombrar", "Bienvenido a Simple Recipes", "La configuración comprueba la IA y muestra idiomas verificados. La colección funciona inmediatamente sin IA."])),
}


def text(key, language="en"):
    return TEXT.get(language, TEXT["en"]).get(key, TEXT["en"].get(key, key))

KEYS.append('group_category')
for language, label in {'en': 'Group by category', 'de': 'Nach Kategorie gruppieren', 'fr': 'Grouper par catégorie', 'it': 'Raggruppa per categoria', 'es': 'Agrupar por categoría'}.items():
    TEXT[language]['group_category'] = label

for key, labels in {
    'result_count': ['Results', 'Ergebnisse', 'Résultats', 'Risultati', 'Resultados'],
    'search_language': ['Preferred language', 'Bevorzugte Sprache', 'Langue préférée', 'Lingua preferita', 'Idioma preferido'],
    'all_languages': ['All languages', 'Alle Sprachen', 'Toutes les langues', 'Tutte le lingue', 'Todos los idiomas'],
}.items():
    KEYS.append(key)
    for language, label in zip(['en', 'de', 'fr', 'it', 'es'], labels):
        TEXT[language][key] = label

KEYS.append('all_channels')
for language, label in zip(['en', 'de', 'fr', 'it', 'es'], ['All channels', 'Alle Kanäle', 'Toutes les chaînes', 'Tutti i canali', 'Todos los canales']):
    TEXT[language]['all_channels'] = label

for key, labels in {
    'preview_video': ['▶ Preview video', '▶ Video ansehen', '▶ Voir la vidéo', '▶ Guarda il video', '▶ Ver vídeo'],
    'choose_video': ['Use for import', 'Zum Import auswählen', 'Choisir pour importer', 'Scegli per importare', 'Elegir para importar'],
}.items():
    KEYS.append(key)
    for language, label in zip(['en', 'de', 'fr', 'it', 'es'], labels):
        TEXT[language][key] = label

KEYS.append('font_size')
for language, label in zip(['en', 'de', 'fr', 'it', 'es'], ['Text size', 'Schriftgröße', 'Taille du texte', 'Dimensione del testo', 'Tamaño del texto']):
    TEXT[language]['font_size'] = label

for key, labels in {
    'translation_unavailable': [
        'The selected AI model is unavailable or its translation check failed. Start your local AI server or choose an available provider in Settings. The recipe was not changed.',
        'Das gewählte KI-Modell ist nicht erreichbar oder seine Sprachprüfung ist fehlgeschlagen. Starte deinen lokalen KI-Server oder wähle in den Einstellungen einen verfügbaren Anbieter. Das Rezept wurde nicht geändert.',
        'Le modèle IA est indisponible ou sa vérification a échoué. Démarrez votre serveur local ou choisissez un fournisseur disponible. La recette reste inchangée.',
        'Il modello IA non è disponibile o la verifica è fallita. Avvia il server locale o scegli un fornitore disponibile. La ricetta non è stata modificata.',
        'El modelo no está disponible o falló la comprobación. Inicia el servidor local o elige otro proveedor. La receta no se ha modificado.'],
    'translation_incomplete': [
        'The AI returned incomplete ingredients or instructions. The original recipe was kept. Try another model.',
        'Die KI hat unvollständige Zutaten oder Kochanweisungen geliefert. Das ursprüngliche Rezept bleibt erhalten. Versuche ein anderes Modell.',
        'L’IA a renvoyé des ingrédients ou instructions incomplets. La recette originale est conservée. Essayez un autre modèle.',
        'L’IA ha restituito ingredienti o istruzioni incompleti. La ricetta originale è conservata. Prova un altro modello.',
        'La IA devolvió ingredientes o instrucciones incompletos. Se conserva la receta original. Prueba otro modelo.'],
}.items():
    KEYS.append(key)
    for language, label in zip(['en', 'de', 'fr', 'it', 'es'], labels):
        TEXT[language][key] = label

for key, labels in {
    'claude': ['Claude — existing Claude login', 'Claude — vorhandene Claude-Anmeldung', 'Claude — connexion Claude existante', 'Claude — accesso Claude esistente', 'Claude — sesión de Claude existente'],
    'importing': ['Importing recipe…', 'Rezept wird importiert…', 'Importation de la recette…', 'Importazione della ricetta…', 'Importando receta…'],
    'reprocessing': ['AI is reprocessing the recipe…', 'KI überarbeitet das Rezept…', 'L’IA retraite la recette…', 'L’IA rielabora la ricetta…', 'La IA está reprocesando la receta…'],
    'searching': ['Searching YouTube…', 'YouTube wird durchsucht…', 'Recherche sur YouTube…', 'Ricerca su YouTube…', 'Buscando en YouTube…'],
    'progress_starting_ai': ['Starting the local AI server and loading the model…', 'Lokaler KI-Server wird gestartet und Modell geladen…', 'Démarrage du serveur IA local et chargement du modèle…', 'Avvio del server IA locale e caricamento del modello…', 'Iniciando el servidor de IA local y cargando el modelo…'],
    'progress_reading': ['Reading the source (page, video description and transcript)…', 'Quelle wird gelesen (Seite, Videobeschreibung und Transkript)…', 'Lecture de la source (page, description et transcription)…', 'Lettura della fonte (pagina, descrizione e trascrizione)…', 'Leyendo la fuente (página, descripción y transcripción)…'],
    'progress_checking': ['Checking the AI model and target language…', 'KI-Modell und Zielsprache werden geprüft…', 'Vérification du modèle IA et de la langue cible…', 'Verifica del modello IA e della lingua di destinazione…', 'Comprobando el modelo de IA y el idioma de destino…'],
    'progress_ai': ['AI is extracting and translating ingredients and steps… this can take a minute.', 'KI extrahiert und übersetzt Zutaten und Schritte… das kann eine Minute dauern.', 'L’IA extrait et traduit ingrédients et étapes… cela peut prendre une minute.', 'L’IA estrae e traduce ingredienti e passaggi… può richiedere un minuto.', 'La IA extrae y traduce ingredientes y pasos… puede tardar un minuto.'],
    'progress_saving': ['Saving the recipe…', 'Rezept wird gespeichert…', 'Enregistrement de la recette…', 'Salvataggio della ricetta…', 'Guardando la receta…'],
    'ai_no_recipe': ['The AI found no ingredients or steps in this source (page, video description or transcript). The original text was saved; you can edit it or try another source.', 'Die KI hat in dieser Quelle (Seite, Videobeschreibung oder Transkript) keine Zutaten oder Schritte gefunden. Der Originaltext wurde gespeichert; du kannst ihn bearbeiten oder eine andere Quelle versuchen.', 'L’IA n’a trouvé ni ingrédients ni étapes dans cette source. Le texte original a été enregistré.', 'L’IA non ha trovato ingredienti o passaggi in questa fonte. Il testo originale è stato salvato.', 'La IA no encontró ingredientes ni pasos en esta fuente. Se guardó el texto original.'],
    'ai_request_failed': ['The AI request failed (login, usage limit, timeout or invalid answer). The original text was saved; use the AI button in the library to retry.', 'Die KI-Anfrage ist fehlgeschlagen (Anmeldung, Nutzungslimit, Zeitüberschreitung oder ungültige Antwort). Der Originaltext wurde gespeichert; über die KI-Schaltfläche in der Sammlung erneut versuchen.', 'La requête IA a échoué (connexion, quota, délai ou réponse invalide). Le texte original a été enregistré ; réessayez depuis la collection.', 'La richiesta IA non è riuscita (accesso, limite, timeout o risposta non valida). Il testo originale è stato salvato; riprova dalla raccolta.', 'La solicitud de IA falló (sesión, límite, tiempo de espera o respuesta no válida). Se guardó el texto original; reinténtalo desde la colección.'],
    'pick_hint': ['Click a video to use it for import · double-click to watch', 'Video anklicken, um es zu importieren · Doppelklick zum Ansehen', 'Cliquez sur une vidéo pour l’importer · double-clic pour la voir', 'Clicca un video per importarlo · doppio clic per guardarlo', 'Haz clic en un vídeo para importarlo · doble clic para verlo'],
    'video_picked': ['Video link added — press Import to start.', 'Videolink übernommen — Importieren drücken, um zu starten.', 'Lien ajouté — appuyez sur Importer.', 'Link aggiunto — premi Importa.', 'Enlace añadido — pulsa Importar.'],
}.items():
    KEYS.append(key)
    for language, label in zip(['en', 'de', 'fr', 'it', 'es'], labels):
        TEXT[language][key] = label

for key, labels in {
    'check_languages': ['Check languages', 'Sprachen prüfen', 'Vérifier les langues', 'Verifica lingue', 'Comprobar idiomas'],
    'ai_settings': ['AI settings…', 'KI-Einstellungen…', 'Réglages IA…', 'Impostazioni IA…', 'Ajustes de IA…'],
    'ai_off_hint': ['AI is off: recipes are saved as found. Choose a provider in AI settings to extract and translate them.',
                    'KI ist aus: Rezepte werden unverändert gespeichert. In den KI-Einstellungen einen Anbieter wählen, um sie zu extrahieren und zu übersetzen.',
                    'IA désactivée : les recettes sont enregistrées telles quelles. Choisissez un fournisseur dans les réglages IA.',
                    'IA disattivata: le ricette vengono salvate così come sono. Scegli un fornitore nelle impostazioni IA.',
                    'IA desactivada: las recetas se guardan tal cual. Elige un proveedor en los ajustes de IA.'],
    'video_empty': ['Search for a dish — matching recipe videos appear here.', 'Nach einem Gericht suchen — passende Rezeptvideos erscheinen hier.',
                    'Cherchez un plat — les vidéos de recettes apparaissent ici.', 'Cerca un piatto — i video delle ricette appariranno qui.',
                    'Busca un plato — los vídeos de recetas aparecerán aquí.'],
    'categories_heading': ['Categories', 'Kategorien', 'Catégories', 'Categorie', 'Categorías'],
    'data_heading': ['Data & backup', 'Daten & Sicherung', 'Données et sauvegarde', 'Dati e backup', 'Datos y copia de seguridad'],
    'filter_results': ['Filter these videos by title…', 'Diese Videos nach Titel filtern…', 'Filtrer ces vidéos par titre…', 'Filtra questi video per titolo…', 'Filtrar estos vídeos por título…'],
    'maintenance_heading': ['Setup & reset', 'Einrichtung & Zurücksetzen', 'Configuration et réinitialisation', 'Configurazione e ripristino', 'Configuración y restablecimiento'],
}.items():
    KEYS.append(key)
    for language, label in zip(['en', 'de', 'fr', 'it', 'es'], labels):
        TEXT[language][key] = label

# Claude joined Codex as a signed-in provider; local models now follow a GPU release rule.
for language, label in {
    'en': 'Online AI receives the recipe text and uses your account limits. Claude and Codex keep their own logins; the app never copies them. Other API keys are stored in your private database. Local models run on your GPU: only one is loaded at a time, and it is unloaded when this window is hidden or closed.',
    'de': 'Online-KI erhält den Rezepttext und nutzt Ihre Kontingente. Claude und Codex verwalten ihre Anmeldung selbst; die App kopiert sie nie. Andere API-Schlüssel liegen in Ihrer privaten Datenbank. Lokale Modelle laufen auf Ihrer GPU: Es ist immer nur eines geladen, und es wird entladen, sobald dieses Fenster ausgeblendet oder geschlossen wird.',
    'fr': 'L’IA en ligne reçoit le texte et utilise votre quota. Claude et Codex gèrent leur connexion ; les autres clés API sont stockées dans votre base privée. Les modèles locaux tournent sur votre GPU : un seul est chargé à la fois et il est déchargé quand cette fenêtre est masquée.',
    'it': 'L’IA online riceve il testo e usa la quota del tuo account. Claude e Codex gestiscono l’accesso; le altre chiavi API sono nel database privato. I modelli locali usano la GPU: ne viene caricato uno alla volta e viene scaricato quando la finestra è nascosta.',
    'es': 'La IA online recibe el texto y usa tu cuota. Claude y Codex gestionan su sesión; las otras claves API se guardan en la base privada. Los modelos locales usan tu GPU: solo se carga uno a la vez y se descarga al ocultar esta ventana.',
}.items():
    TEXT[language]['privacy'] = label
