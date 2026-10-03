# Simple Recipes user guide

## Start and setup

Click the chef hat in the Omarchy bar to open the native recipe window. Click again or press Escape to hide it. Right-click always opens it. The window is a Python desktop application; it needs no browser or web server. Hiding it lets a running import finish.

On the first opening of an unconfigured installation, choose an interface language and optionally an AI provider. Existing configuration skips this assistant. You can start without AI. The setup assistant is also available in Settings. Help contains this guide.

Interfaces are available in English, German, French, Italian and Spanish. Set your preferred interface in Settings independently of the recipe translation language.

## Choose an AI model

In Settings, choose the provider and model. For Codex, your existing ChatGPT login is used; no API key is needed. If missing, run `codex login` in a terminal. For local models, a separately configured llama.cpp router and llama-server.service must be available; the app starts the service when needed. For other online providers enter the appropriate API key; custom providers also need their endpoint.

Click the button to select the model and check languages. Local models are switched before the check. The supported target list appears in both Settings and Import. Chinese, Japanese and other languages appear when their sample passes. Twenty-one target languages are checked. Changing model or credentials clears the old choices until checked again. Checks make model requests and may use account limits or incur charges.

Choose your target before enabling AI import. A successful sample is a useful check, not a guarantee of perfect translation. Failed checks leave the target unverified. Check again if the connection or model changes.

## Import and browse

Import is the first tab and opens when you show the window. Paste a public recipe webpage or video link, and click Import. Structured recipe webpages can be imported without AI. With a configured AI provider, AI processing is selected automatically unless you turned it off. One import extracts and separates the ingredients and instructions, then translates both into the selected target; no separate reprocessing click is needed. Labelled sections can also be separated without AI. Video search provides thumbnail previews, a text filter and channel grouping; select a result and click Use for import to use its URL. The status line reports progress. Imported raw content is preserved if AI processing fails.

The second tab, Library, searches titles, ingredients and tags. Recipe cards show image previews with emoji fallbacks, category, duration and tags. Group by category can be toggled; headings show each category and its recipe count. Select a recipe and change the Category dropdown beneath its details to reassign it immediately. Filter favourites or category, and choose a sort order. Select a recipe to read its ingredients and instructions. Mark favourites and tried recipes, edit entries, or create a recipe manually. Cooking view provides steps and a timer. The source button opens the original recipe. Sharing opens WhatsApp with the ingredient list and the saved phone number.

Reprocessing uses your selected model and verified target. The existing recipe is preserved if processing fails. Delete asks for confirmation.

## Categories, phone and backups

Settings is the third tab and manages categories and a phone number for sharing. Help is the last tab. A blank number clears it. German local numbers are converted to +49; international numbers can start with + or 00.

Use SQLite backup for a complete, consistent copy, including settings and API keys. Keep it private. JSON export contains recipes without credentials; JSON restore merges recipes and skips duplicate source links. For complete SQLite restoration, stop the service first and replace `~/.local/share/simple-recipes/data/rezepte.db` with your backup. Preserve a copy of the current database before replacing it.

Reset recipes and settings asks for confirmation and clears all plugin recipes, categories, the phone number, API keys and preferences. This does not erase the separate original Meine Rezepte app or Codex login.

## Troubleshooting

If the chef hat does not open the window, rerun the installation's setup script, then inspect:

```sh
systemctl --user status simple-recipes.service
journalctl --user -u simple-recipes.service -n 40 --no-pager
```

If a model or language check fails, check the provider login/API key, local server and chosen model. Open the Library to continue without AI. Missing target languages mean the sample did not pass; try checking again or another model.

To stop the app completely:

```sh
bash ~/.config/omarchy/plugins/ubruckhaus.simple-recipes/scripts/stop.sh
```

The next chef hat click starts it again. No login autostart or HTTP listener is required. Installation updates keep the database outside the plugin directory. The Python runtime and SQLite file are local; SQLite requires no separate server.

Completed setup is remembered for everyday use. Reopening restores the provider, model and last target without repeating language discovery. Use Settings to refresh the language list; AI imports still verify their chosen target.

YouTube search: select 1–50 results and a preferred language (All languages by default). Results appear in two columns with thumbnails, channel names and video duration. Search language is a preference, not a strict spoken-language filter. The result count and language are remembered after searching.

Select a YouTube result and click Preview video, or double-click it (Enter also works), to watch it in your browser before importing. Use for import copies the selected link into the import field; it does not import until you click Import.

Cooking mode uses larger text (26 px by default). Its Text size control adjusts instructions and timer from 18 to 48 px and remembers your choice. Instruction text can also be selected and copied.

Translate with AI translates ingredients and every cooking step into the selected target language. Measurement conventions follow the interface: English uses US kitchen units, while German, French, Italian and Spanish use metric units and Celsius. Incomplete translations leave the existing recipe unchanged.

Interface language: the five built-in interfaces remain available without AI. After a model language check, its verified targets also appear in the interface selector. The first selection of an additional language generates and saves translated labels with that model; later selections use the cached translation. Incomplete generation keeps the previous interface. Choosing an interface language also sets the recipe target to the same language; the target can then be changed separately. Arabic uses a right-to-left layout. The manual itself remains in English.

Local AI lifecycle: hiding or closing the recipe window stops llama-server.service to release GPU memory. Running jobs finish first. The next local AI operation starts the configured server and loads the saved model automatically. Stopping the recipe service also stops that AI service. Online providers are unaffected. Translation failures now show an explicit message and preserve the original recipe.

Selecting a model or target language enables AI import. If an AI import fails, the app displays a notice and keeps the source recipe. Translate with AI retrieves the original source when saved ingredients or preparation are missing.

Reset and the first-run setup clear YouTube search text, results, filters, channel selection and the import URL. Search defaults return to 10 results and all languages. Choosing No AI in setup clears the saved provider and model selection.
