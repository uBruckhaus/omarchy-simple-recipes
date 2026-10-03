(() => {
  const tr = window.recipeT;
  // HTML-escaping helper: every dynamic value that is inserted via innerHTML
  // (recipe data from scraped pages, YouTube results, step texts) must go
  // through this to prevent stored XSS.
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));

  // Clean URL parameters after page load to prevent repeating notifications/errors on refresh
  if (window.history.replaceState) {
    const url = new URL(window.location.href);
    if (url.searchParams.has('error') || url.searchParams.has('notice')) {
      url.searchParams.delete('error');
      url.searchParams.delete('notice');
      window.history.replaceState({}, document.title, url.pathname + url.search);
    }
  }

  // Automatically add close button and fade out error/notice banners
  document.querySelectorAll('.error, .notice').forEach(el => {
    const closeBtn = document.createElement('span');
    closeBtn.textContent = '✕';
    closeBtn.style.marginLeft = 'auto';
    closeBtn.style.cursor = 'pointer';
    closeBtn.style.paddingLeft = '15px';
    closeBtn.style.fontWeight = 'bold';
    closeBtn.addEventListener('click', () => el.remove());
    
    el.style.display = 'flex';
    el.style.alignItems = 'center';
    el.appendChild(closeBtn);

    setTimeout(() => {
      el.style.transition = 'opacity 0.5s ease';
      el.style.opacity = '0';
      setTimeout(() => el.remove(), 500);
    }, 8000);
  });

  // --- Cooking Mode (Kochmodus) ---
  const startCookingBtn = document.querySelector('#start-cooking');
  const cookingOverlay = document.querySelector('#cooking-overlay');
  
  if (startCookingBtn && cookingOverlay) {
    const closeCookingBtn = document.querySelector('#close-cooking');
    const cookingPrevBtn = document.querySelector('#cooking-prev');
    const cookingNextBtn = document.querySelector('#cooking-next');
    const cookingStepBadge = document.querySelector('#cooking-step-badge');
    const cookingProgressBar = document.querySelector('#cooking-progress-bar');
    const cookingStepNum = document.querySelector('#cooking-step-num');
    const cookingStepText = document.querySelector('#cooking-step-text');
    
    // Parse steps from data-steps attribute
    let steps = [];
    try {
      steps = JSON.parse(cookingOverlay.dataset.steps || '[]');
    } catch (e) {
      console.error("Failed to parse cooking steps:", e);
    }
    
    let currentStep = 0;
    let wakeLock = null;
    let activeTimers = {}; // Map of "stepIdx-timeIdx" -> intervalId
    
    // Web Audio API Alarm Synthesizer
    const playAlarmChime = () => {
      try {
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        if (!AudioContext) return;
        const ctx = new AudioContext();
        
        // Play 3 clean, pleasant bell chimes
        const playBell = (time, freq) => {
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          osc.connect(gain);
          gain.connect(ctx.destination);
          
          osc.type = 'sine';
          osc.frequency.setValueAtTime(freq, time);
          
          gain.gain.setValueAtTime(0.5, time);
          gain.gain.exponentialRampToValueAtTime(0.01, time + 0.8);
          
          osc.start(time);
          osc.stop(time + 0.8);
        };
        
        const now = ctx.currentTime;
        playBell(now, 880);       // A5
        playBell(now + 0.25, 987.77); // B5
        playBell(now + 0.5, 1318.51); // E6
      } catch (e) {
        console.error("Audio chime playback failed:", e);
      }
    };
    
    // Screen Wake Lock API helpers
    const requestWakeLock = async () => {
      try {
        if ('wakeLock' in navigator) {
          wakeLock = await navigator.wakeLock.request('screen');
        }
      } catch (err) {
        console.warn('Wake Lock request failed:', err);
      }
    };
    
    const releaseWakeLock = async () => {
      try {
        if (wakeLock) {
          await wakeLock.release();
          wakeLock = null;
        }
      } catch (err) {
        console.warn('Wake Lock release failed:', err);
      }
    };
    
    // Time regex parser: e.g. "15 Minuten", "1 Stunde", "5 - 10 min", "2 Stunden"
    const parseTimes = (text) => {
      const regex = /(\d+(?:[.,-]\d+)?)\s*(?:Minuten|Min\.?|min|minutes|minute|mins|Stunden|Std\.?|std|hours|hour|hrs|Stunde)/gi;
      const times = [];
      let match;
      while ((match = regex.exec(text)) !== null) {
        const valueStr = match[1].replace(',', '.');
        const rangeParts = valueStr.split('-');
        let val = parseFloat(rangeParts[rangeParts.length - 1]); // take high end of range
        
        const unit = match[0].toLowerCase();
        let seconds = 0;
        if (unit.includes('std') || unit.includes('stund') || unit.includes('hour') || unit.includes('hr')) {
          seconds = Math.round(val * 3600);
        } else {
          seconds = Math.round(val * 60);
        }
        
        if (seconds > 0) {
          times.push({
            text: match[0],
            seconds: seconds
          });
        }
      }
      return times;
    };
    
    // Timer Chip Engine
    const setupStepTimer = (stepTextElement, stepIdx) => {
      const text = stepTextElement.textContent;
      const parsedTimes = parseTimes(text);
      if (parsedTimes.length === 0) return;
      
      // We will parse the text and replace the matches with custom timer buttons
      let html = text;
      
      // Sort times descending by length of text to avoid sub-string replacement issues
      parsedTimes.sort((a, b) => b.text.length - a.text.length);
      
      parsedTimes.forEach((pt, timeIdx) => {
        const btnId = `timer-${stepIdx}-${timeIdx}`;
        const ptEscaped = pt.text.replace(/[-\/\\^$*+?.()|[\]{}]/g, '\\$&');
        const regex = new RegExp(ptEscaped, 'g');
        
        html = html.replace(regex, `<button class="timer-btn" id="${btnId}" data-duration="${pt.seconds}">⏱️ ${esc(pt.text)}</button>`);
      });
      
      stepTextElement.innerHTML = html;
      
      // Add event listeners to the generated buttons
      parsedTimes.forEach((pt, timeIdx) => {
        const btnId = `timer-${stepIdx}-${timeIdx}`;
        const btn = stepTextElement.querySelector(`#${btnId}`);
        if (!btn) return;
        
        let secondsLeft = pt.seconds;
        let timerState = 'idle'; // idle, running, paused, expired
        let intervalId = null;
        
        const updateBtnUI = () => {
          btn.className = `timer-btn ${timerState}`;
          if (timerState === 'idle') {
            btn.textContent = `⏱️ ${pt.text}`;
          } else if (timerState === 'running') {
            const m = Math.floor(secondsLeft / 60);
            const s = secondsLeft % 60;
            btn.textContent = `⏳ ${m}:${String(s).padStart(2, '0')}`;
          } else if (timerState === 'paused') {
            const m = Math.floor(secondsLeft / 60);
            const s = secondsLeft % 60;
            btn.textContent = `⏸️ ${m}:${String(s).padStart(2, '0')}`;
          } else if (timerState === 'expired') {
            const isEn = (document.documentElement.lang || 'en').startsWith('en');
            btn.textContent = tr('timer_done');
          }
        };
        
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          
          if (timerState === 'idle' || timerState === 'paused') {
            timerState = 'running';
            updateBtnUI();
            
            // Store active timer interval so we can clear it when exiting Cooking Mode
            intervalId = setInterval(() => {
              secondsLeft--;
              if (secondsLeft <= 0) {
                clearInterval(intervalId);
                intervalId = null;
                timerState = 'expired';
                updateBtnUI();
                playAlarmChime();
              } else {
                updateBtnUI();
              }
            }, 1000);
            
            // Add interval to global list for cleanup
            activeTimers[`${stepIdx}-${timeIdx}`] = intervalId;
            
          } else if (timerState === 'running') {
            timerState = 'paused';
            clearInterval(intervalId);
            intervalId = null;
            delete activeTimers[`${stepIdx}-${timeIdx}`];
            updateBtnUI();
          } else if (timerState === 'expired') {
            timerState = 'idle';
            secondsLeft = pt.seconds;
            updateBtnUI();
          }
        });
      });
    };
    
    // Overlay Navigation
    const updateCookingUI = () => {
      if (steps.length === 0) return;
      const isEn = (document.documentElement.lang || 'en').startsWith('en');
      
      // Update badge, step number, step text
      cookingStepBadge.textContent = `${tr('cooking_step')} ${currentStep + 1} ${tr('cooking_of')} ${steps.length}`;
      cookingStepNum.textContent = currentStep + 1;
      cookingStepText.textContent = steps[currentStep];
      
      // Setup the interactive timer badges in text
      setupStepTimer(cookingStepText, currentStep);
      
      // Update progress bar width
      const progressPercent = ((currentStep + 1) / steps.length) * 100;
      cookingProgressBar.style.width = `${progressPercent}%`;
      
      // Enable/disable navigation buttons
      cookingPrevBtn.disabled = currentStep === 0;
      cookingNextBtn.textContent = currentStep === steps.length - 1 ? tr('cooking_done') : tr('cooking_next');
    };
    
    const nextStep = () => {
      if (currentStep < steps.length - 1) {
        currentStep++;
        updateCookingUI();
      } else {
        closeCooking();
      }
    };
    
    const prevStep = () => {
      if (currentStep > 0) {
        currentStep--;
        updateCookingUI();
      }
    };
    
    const openCooking = async () => {
      currentStep = 0;
      cookingOverlay.classList.add('active');
      document.body.style.overflow = 'hidden'; // prevent background scrolling
      updateCookingUI();
      await requestWakeLock();
    };
    
    const closeCooking = async () => {
      // Clear all active timers
      Object.keys(activeTimers).forEach(key => {
        clearInterval(activeTimers[key]);
      });
      activeTimers = {};
      
      cookingOverlay.classList.remove('active');
      document.body.style.overflow = '';
      await releaseWakeLock();
    };
    
    // Add event listeners for controls
    startCookingBtn.addEventListener('click', openCooking);
    closeCookingBtn.addEventListener('click', closeCooking);
    cookingPrevBtn.addEventListener('click', prevStep);
    cookingNextBtn.addEventListener('click', nextStep);

    // Touch swipe navigation for cooking mode (iPhone / mobile)
    let touchStartX = 0;
    let touchStartY = 0;
    cookingOverlay.addEventListener('touchstart', (e) => {
      if (e.changedTouches && e.changedTouches.length > 0) {
        touchStartX = e.changedTouches[0].screenX;
        touchStartY = e.changedTouches[0].screenY;
      }
    }, { passive: true });

    cookingOverlay.addEventListener('touchend', (e) => {
      if (e.changedTouches && e.changedTouches.length > 0) {
        const diffX = e.changedTouches[0].screenX - touchStartX;
        const diffY = e.changedTouches[0].screenY - touchStartY;
        // Check for horizontal swipe (> 45px threshold and mainly horizontal)
        if (Math.abs(diffX) > 45 && Math.abs(diffX) > Math.abs(diffY)) {
          if (diffX < 0) {
            nextStep(); // Swipe left -> Next step
          } else {
            prevStep(); // Swipe right -> Previous step
          }
        }
      }
    }, { passive: true });
    
    // Keyboard navigation
    window.addEventListener('keydown', (e) => {
      if (!cookingOverlay.classList.contains('active')) return;
      
      if (e.key === 'ArrowRight') {
        nextStep();
      } else if (e.key === 'ArrowLeft') {
        prevStep();
      } else if (e.key === 'Escape') {
        closeCooking();
      } else if (e.key === ' ') {
        // Space bar: if there is an active timer in the step, toggle it!
        const timerBtn = cookingStepText.querySelector('.timer-btn');
        if (timerBtn) {
          e.preventDefault();
          timerBtn.click();
        }
      }
    });
  }

  // --- Portions-Rechner (Portion Calculator) ---
  const servingsSelector = document.querySelector('#servings-selector');
  if (servingsSelector) {
    const servingsDisplay = document.querySelector('#servings-display');
    const servingsMinus = document.querySelector('#servings-minus');
    const servingsPlus = document.querySelector('#servings-plus');
    const ingredientTexts = document.querySelectorAll('.ingredient-text');
    
    const originalText = servingsSelector.dataset.original.trim();
    
    // Parse the original serving count number
    // E.g. "4 Portionen" -> 4, "2 Personen" -> 2, "4" -> 4, "1 Blech" -> 1
    const match = originalText.match(/(\d+(?:[.,]\d+)?)/);
    const originalServings = match ? parseFloat(match[1].replace(',', '.')) : 1;
    let currentServings = originalServings;
    
    // Parse individual ingredient lines and inject spans for quantities
    // E.g. "250g Mehl", "1,5 Liter Milch", "1/2 TL Zimt", "1 Ei"
    ingredientTexts.forEach(el => {
      const text = el.textContent.trim();
      
      // 1. Try mixed fraction first: "1 1/2" or "1 1/4"
      const mixedFracMatch = text.match(/^(\d+)\s+(\d+)\/(\d+)\b/);
      if (mixedFracMatch) {
        const val = parseFloat(mixedFracMatch[1]) + (parseFloat(mixedFracMatch[2]) / parseFloat(mixedFracMatch[3]));
        const rest = text.substring(mixedFracMatch[0].length);
        el.innerHTML = `<span class="scaled-qty" data-base-val="${val}">${mixedFracMatch[1]} ${mixedFracMatch[2]}/${mixedFracMatch[3]}</span>${rest}`;
        return;
      }
      
      // 2. Try fraction: "1/2", "1/4", "3/4"
      const fracMatch = text.match(/^(\d+)\/(\d+)\b/);
      if (fracMatch) {
        const val = parseFloat(fracMatch[1]) / parseFloat(fracMatch[2]);
        const rest = text.substring(fracMatch[0].length);
        el.innerHTML = `<span class="scaled-qty" data-base-val="${val}">${fracMatch[0]}</span>${rest}`;
        return;
      }
      
      // 3. Try normal decimal or integer: e.g. "1,5", "1.5", "250"
      const numMatch = text.match(/^(\d+(?:[.,]\d+)?)\b/);
      if (numMatch) {
        const val = parseFloat(numMatch[1].replace(',', '.'));
        const rest = text.substring(numMatch[0].length);
        el.innerHTML = `<span class="scaled-qty" data-base-val="${val}">${numMatch[1]}</span>${rest}`;
        return;
      }
    });
    
    // Format helper to display scaled quantities nicely
    const formatQty = (val) => {
      let rounded = Math.round(val * 100) / 100;
      return String(rounded).replace('.', ',');
    };
    
    const updateServings = (newCount) => {
      if (newCount < 0.25) return;
      currentServings = Math.round(newCount * 100) / 100;
      
      let updatedText = originalText.replace(/(\d+(?:[.,]\d+)?)/, formatQty(currentServings));
      servingsDisplay.textContent = updatedText;
      
      const ratio = currentServings / originalServings;
      document.querySelectorAll('.scaled-qty').forEach(el => {
        const baseVal = parseFloat(el.dataset.baseVal);
        el.textContent = formatQty(baseVal * ratio);
      });
    };
    
    servingsMinus.addEventListener('click', () => {
      let step = 1;
      if (currentServings <= 2) step = 0.5;
      if (currentServings <= 1) step = 0.25;
      updateServings(currentServings - step);
    });
    
    servingsPlus.addEventListener('click', () => {
      let step = 1;
      if (currentServings < 1) step = 0.25;
      else if (currentServings < 2) step = 0.5;
      updateServings(currentServings + step);
    });
  }

  // --- Such-Autovervollständigung (Search Autocomplete) ---
  const searchInput = document.querySelector('#search-input');
  const suggestionsBox = document.querySelector('#search-suggestions');
  
  if (searchInput && suggestionsBox) {
    let debounceTimer = null;
    let highlightedIndex = -1;
    
    const fetchSuggestions = (query) => {
      if (!query.trim()) {
        suggestionsBox.innerHTML = '';
        suggestionsBox.hidden = true;
        highlightedIndex = -1;
        return;
      }
      
      fetch(`/api/recipes/search?q=${encodeURIComponent(query.trim())}`)
        .then(res => res.json())
        .then(data => {
          if (data.length === 0) {
            suggestionsBox.innerHTML = '';
            suggestionsBox.hidden = true;
            highlightedIndex = -1;
            return;
          }
          
          suggestionsBox.innerHTML = data.map((item, idx) => `
            <a href="/recipe/${esc(item.id)}" class="suggestion-item" data-index="${idx}">
              <div class="suggestion-emoji">${esc(item.emoji)}</div>
              <div class="suggestion-info">
                <span class="suggestion-title">${esc(item.title)}</span>
                <span class="suggestion-category">${esc(item.category)}</span>
              </div>
            </a>
          `).join('');
          suggestionsBox.hidden = false;
          highlightedIndex = -1;
        })
        .catch(err => console.error("Suggestions fetch error:", err));
    };
    
    searchInput.addEventListener('input', () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        fetchSuggestions(searchInput.value);
      }, 150);
    });
    
    const updateHighlight = (items) => {
      items.forEach((item, idx) => {
        item.classList.toggle('highlighted', idx === highlightedIndex);
        if (idx === highlightedIndex) {
          item.scrollIntoView({ block: 'nearest' });
        }
      });
    };
    
    searchInput.addEventListener('keydown', (e) => {
      if (suggestionsBox.hidden) return;
      
      const items = suggestionsBox.querySelectorAll('.suggestion-item');
      if (items.length === 0) return;
      
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        highlightedIndex = (highlightedIndex + 1) % items.length;
        updateHighlight(items);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        highlightedIndex = (highlightedIndex - 1 + items.length) % items.length;
        updateHighlight(items);
      } else if (e.key === 'Enter') {
        if (highlightedIndex >= 0 && highlightedIndex < items.length) {
          e.preventDefault();
          items[highlightedIndex].click();
        }
      } else if (e.key === 'Escape') {
        suggestionsBox.hidden = true;
        highlightedIndex = -1;
      }
    });
    
    document.addEventListener('click', (e) => {
      if (e.target !== searchInput && !suggestionsBox.contains(e.target)) {
        suggestionsBox.hidden = true;
        highlightedIndex = -1;
      }
    });
  }

  // --- AJAX Page reloading (No-Reload) ---
  const filtersForm = document.querySelector('.filters');
  const recipesContainer = document.querySelector('#recipes-container');
  const categoryNav = document.querySelector('.category-nav');
  
  if (filtersForm && recipesContainer) {
    const updateRecipes = async (urlParams) => {
      const useTransition = !!document.startViewTransition;
      
      if (!useTransition) {
        recipesContainer.style.transition = 'opacity 0.15s ease';
        recipesContainer.style.opacity = '0.3';
      }
      
      const url = new URL(window.location.href);
      for (const key of Array.from(url.searchParams.keys())) {
        url.searchParams.delete(key);
      }
      for (const [key, val] of urlParams.entries()) {
        if (val) url.searchParams.set(key, val);
      }
      url.searchParams.delete('error');
      url.searchParams.delete('notice');
      
      window.history.pushState({}, '', url.toString());
      
      url.searchParams.set('ajax', '1');
      
      try {
        const response = await fetch(url.toString(), {
          headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });
        if (response.ok) {
          const html = await response.text();
          if (useTransition) {
            document.startViewTransition(() => {
              recipesContainer.innerHTML = html;
            });
          } else {
            recipesContainer.innerHTML = html;
          }
        }
      } catch (err) {
        console.error("AJAX recipe update failed:", err);
      } finally {
        if (!useTransition) {
          recipesContainer.style.opacity = '1';
        }
      }
    };
    
    filtersForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const formData = new FormData(filtersForm);
      const urlParams = new URLSearchParams(formData);
      updateRecipes(urlParams);
    });
    
    const sortSelect = filtersForm.querySelector('select[name="sort"]');
    if (sortSelect) {
      sortSelect.addEventListener('change', () => {
        const formData = new FormData(filtersForm);
        const urlParams = new URLSearchParams(formData);
        updateRecipes(urlParams);
      });
    }
    
    document.querySelectorAll('.view-chip').forEach(chip => {
      chip.replaceWith(chip.cloneNode(true));
    });
    
    document.querySelectorAll('.view-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        const viewInput = document.querySelector('#view-input');
        if (viewInput) {
          viewInput.value = chip.dataset.value;
          chip.parentNode.querySelectorAll('.view-chip').forEach(c => c.classList.remove('active'));
          chip.classList.add('active');
          
          const formData = new FormData(filtersForm);
          const urlParams = new URLSearchParams(formData);
          updateRecipes(urlParams);
        }
      });
    });
    
    if (categoryNav) {
      categoryNav.addEventListener('click', (e) => {
        const link = e.target.closest('a');
        if (!link) return;
        
        e.preventDefault();
        
        categoryNav.querySelectorAll('a').forEach(a => a.classList.remove('active'));
        link.classList.add('active');
        
        const hrefUrl = new URL(link.href);
        const urlParams = hrefUrl.searchParams;
        
        const catValue = urlParams.get('category') || '';
        const formCatInput = filtersForm.querySelector('input[name="category"]');
        if (formCatInput) formCatInput.value = catValue;
        
        const viewValue = urlParams.get('view') || 'flat';
        const formViewInput = filtersForm.querySelector('input[name="view"]');
        if (formViewInput) formViewInput.value = viewValue;
        
        const switcher = document.querySelector('.view-switcher');
        if (switcher) {
          switcher.style.display = catValue ? 'none' : 'inline-flex';
        }
        
        updateRecipes(urlParams);
      });
    }
    
    window.updateRecipesGlobal = updateRecipes;
    
    const favoritesToggleBtn = document.querySelector('#favorites-toggle-btn');
    const favoritesInput = document.querySelector('#favorites-input');
    if (favoritesToggleBtn && favoritesInput) {
      favoritesToggleBtn.addEventListener('click', () => {
        const isActive = favoritesInput.value === '1';
        favoritesInput.value = isActive ? '' : '1';
        favoritesToggleBtn.classList.toggle('active', !isActive);
        
        const formData = new FormData(filtersForm);
        const urlParams = new URLSearchParams(formData);
        updateRecipes(urlParams);
      });
    }
    
    window.addEventListener('popstate', () => {
      const url = new URL(window.location.href);
      
      const qVal = url.searchParams.get('q') || '';
      const qInput = filtersForm.querySelector('input[name="q"]');
      if (qInput) qInput.value = qVal;
      
      const sortVal = url.searchParams.get('sort') || 'newest';
      if (sortSelect) sortSelect.value = sortVal;
      
      const catVal = url.searchParams.get('category') || '';
      const formCatInput = filtersForm.querySelector('input[name="category"]');
      if (formCatInput) formCatInput.value = catVal;
      
      const viewVal = url.searchParams.get('view') || 'flat';
      const formViewInput = filtersForm.querySelector('input[name="view"]');
      if (formViewInput) formViewInput.value = viewVal;
      
      const favVal = url.searchParams.get('favorites') || '';
      if (favoritesInput) favoritesInput.value = favVal;
      if (favoritesToggleBtn) favoritesToggleBtn.classList.toggle('active', favVal === '1');
      
      if (categoryNav) {
        categoryNav.querySelectorAll('a').forEach(a => {
          const aUrl = new URL(a.href);
          const aCat = aUrl.searchParams.get('category') || '';
          a.classList.toggle('active', aCat === catVal);
        });
      }
      
      const switcher = document.querySelector('.view-switcher');
      if (switcher) {
        switcher.style.display = catVal ? 'none' : 'inline-flex';
        switcher.querySelectorAll('.view-chip').forEach(c => {
          c.classList.toggle('active', c.dataset.value === viewVal);
        });
      }
      
      const urlParams = new URLSearchParams(url.search);
      updateRecipes(urlParams);
    });
  }

  // --- 3D-Tilt Hover Effect on Recipe Cards ---
  document.addEventListener('mousemove', (e) => {
    const card = e.target.closest('.card');
    if (!card) return;
    
    const rect = card.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    
    const centerX = rect.width / 2;
    const centerY = rect.height / 2;
    
    const rotateX = ((centerY - y) / centerY) * 6;
    const rotateY = ((x - centerX) / centerX) * 6;
    
    card.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale3d(1.02, 1.02, 1.02) translateY(-6px)`;
  });
  
  document.addEventListener('mouseout', (e) => {
    const card = e.target.closest('.card');
    if (!card) return;
    
    const related = e.relatedTarget;
    if (!related || !card.contains(related)) {
      card.style.transform = 'perspective(1000px) rotateX(0deg) rotateY(0deg) scale3d(1, 1, 1) translateY(0)';
    }
  });

  const categoryAddForm = document.querySelector('#category-add-form');
  document.querySelector('#open-category-add')?.addEventListener('click', () => {
    categoryAddForm.hidden = false;
    categoryAddForm.querySelector('input[name="name"]').focus();
  });
  document.querySelector('#cancel-category-add')?.addEventListener('click', () => { categoryAddForm.hidden = true; });

  const smsDialog = document.querySelector('#sms-dialog');
  const smsForm = document.querySelector('#sms-form');
  
  document.querySelector('#open-sms')?.addEventListener('click', () => {
    if (!smsDialog || !smsForm) return;
    const checkedElements = document.querySelectorAll('.ingredients-list input[type="checkbox"]:checked');
    const ingredientsRadio = smsForm.querySelector('input[value="ingredients"]');
    const recipeRadio = smsForm.querySelector('input[value="recipe"]');
    const ingredientsLabel = ingredientsRadio?.closest('label');
    
    if (checkedElements.length === 0) {
      if (ingredientsRadio) ingredientsRadio.disabled = true;
      if (recipeRadio) recipeRadio.checked = true;
      if (ingredientsLabel) {
        ingredientsLabel.style.opacity = '0.4';
        ingredientsLabel.style.cursor = 'not-allowed';
      }
    } else {
      if (ingredientsRadio) ingredientsRadio.disabled = false;
      if (ingredientsRadio) ingredientsRadio.checked = true;
      if (ingredientsLabel) {
        ingredientsLabel.style.opacity = '1';
        ingredientsLabel.style.cursor = 'pointer';
      }
    }
    smsDialog.showModal();
  });

  smsDialog?.querySelector('.dialog-close')?.addEventListener('click', () => smsDialog.close());
  smsDialog?.querySelector('.dialog-cancel')?.addEventListener('click', () => smsDialog.close());
  smsDialog?.addEventListener('click', event => { if (event.target === smsDialog) smsDialog.close(); });
  smsForm?.querySelector('#sms-phone')?.addEventListener('input', event => event.target.setCustomValidity(''));
  
  smsForm?.addEventListener('submit', event => {
    event.preventDefault();
    const phoneInput = smsForm.querySelector('#sms-phone');
    let phone = phoneInput.value.trim().replace(/[(). /-]/g, '');
    if (phone.startsWith('00')) phone = `+${phone.slice(2)}`;
    else if (phone.startsWith('0')) phone = `+49${phone.slice(1)}`;
    if (!/^\+[1-9]\d{7,14}$/.test(phone)) {
      phoneInput.setCustomValidity('Bitte eine gültige Telefonnummer eingeben.');
      phoneInput.reportValidity();
      return;
    }
    phoneInput.setCustomValidity('');
    
    const content = smsForm.querySelector('[name="share_content"]:checked')?.value;
    let messageText = '';
    
    if (content === 'ingredients') {
      const checkedElements = document.querySelectorAll('.ingredients-list input[type="checkbox"]:checked');
      const checkedIngredients = Array.from(checkedElements).map(el => {
        return el.closest('label').querySelector('.ingredient-text').textContent.trim();
      });
      const recipeTitle = document.querySelector('.recipe-meta-header h1')?.textContent.trim() || 'Rezept';
      messageText = `*${recipeTitle}*\n\nZutaten:\n` + checkedIngredients.map(item => `- ${item}`).join('\n');
    } else {
      messageText = smsForm.dataset.whatsappMessage;
    }
    
    const message = encodeURIComponent(messageText);
    window.open(`https://wa.me/${phone.slice(1)}?text=${message}`, '_blank', 'noopener');
  });

  // Select All / Unselect All Ingredients logic
  const toggleAllBtn = document.querySelector('#toggle-all-ingredients');
  const ingredientCheckboxes = document.querySelectorAll('.ingredients-list input[type="checkbox"]');
  
  const updateToggleAllBtnLabel = () => {
    if (ingredientCheckboxes.length === 0 || !toggleAllBtn) return;
    const allChecked = Array.from(ingredientCheckboxes).every(cb => cb.checked);
    toggleAllBtn.textContent = allChecked ? 'Auswahl aufheben' : 'Alle auswählen';
  };
  
  toggleAllBtn?.addEventListener('click', () => {
    const allChecked = Array.from(ingredientCheckboxes).every(cb => cb.checked);
    ingredientCheckboxes.forEach(cb => {
      cb.checked = !allChecked;
    });
    updateToggleAllBtnLabel();
  });
  
  ingredientCheckboxes.forEach(cb => {
    cb.addEventListener('change', updateToggleAllBtnLabel);
  });
  updateToggleAllBtnLabel();

  // View switcher chips logic
  document.querySelectorAll('.view-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const viewInput = document.querySelector('#view-input');
      if (viewInput) {
        viewInput.value = chip.dataset.value;
        viewInput.form.submit();
      }
    });
  });

  const form = document.querySelector('#import-form');
  const input = document.querySelector('#recipe-url');
  if (form && input) {
    const overlay = document.querySelector('#processing');
    const elapsed = document.querySelector('#elapsed');
    const cancelButton = document.querySelector('#cancel-processing');
    const provider = document.querySelector('#provider');
    let controller = null;
    let timer = null;

    const stopProcessing = () => {
      controller?.abort(); controller = null;
      clearInterval(timer); timer = null;
      overlay.hidden = true;
    };
    cancelButton?.addEventListener('click', () => {
      stopProcessing();
      window.location.href = '/?notice=Verarbeitung+abgebrochen';
    });

    // Lokale Server mit Modellwechsel vs. feste Modellauswahl vs. freie Eingabe
    const isLocalLoadProvider = (p) => p === 'lmstudio' || p === 'llamacpp';
    const isModelSelectProvider = (p) => ['lmstudio', 'llamacpp', 'codex', 'openai', 'gemini', 'groq', 'openrouter', 'deepseek', 'mistral'].includes(p);
    const modelSelectEl = document.querySelector('[name="llm_model"]');
    const applyProviderModelFilter = (p) => {
      if (!modelSelectEl) return;
      const current = modelSelectEl.value;
      let firstVisible = null;
      modelSelectEl.querySelectorAll('option[data-provider]').forEach(opt => {
        const visible = opt.dataset.provider === p;
        opt.hidden = !visible;
        opt.disabled = !visible;
        if (visible && !firstVisible) firstVisible = opt;
      });
      const currentStillVisible = [...modelSelectEl.options].some(o => o.value === current && o.dataset.provider === p);
      if (!currentStillVisible && firstVisible) modelSelectEl.value = firstVisible.value;
    };

    const modelInput = form.querySelector('[name="llm_model"]');
    let loadButton = null;

    const updateLoadButtonState = () => {
      if (!loadButton || !modelInput) return;
      const isEn = (document.documentElement.lang || 'en').startsWith('en');
      const selectedOpt = modelInput.selectedOptions ? modelInput.selectedOptions[0] : null;
      const selectedModel = modelInput.value.trim();
      const isLoaded = selectedOpt?.dataset.active === 'true';
      if (isLoaded) {
        loadButton.textContent = `✓ ${tr('model_active')}`;
        loadButton.classList.remove('needs-load');
      } else if (selectedModel) {
        loadButton.textContent = tr('model_load', {model: selectedModel});
        loadButton.classList.add('needs-load');
      } else {
        loadButton.textContent = tr('model_select');
        loadButton.classList.remove('needs-load');
      }
    };

    const doLoadModel = async (modelToLoad) => {
      const val = (modelToLoad || (modelInput ? modelInput.value : '')).trim();
      if (!val) return;
      const isEn = (document.documentElement.lang || 'en').startsWith('en');
      const currentProvider = provider ? provider.value : 'llamacpp';
      const signal = startProcessing(tr('model_loading'), val);
      const data = new FormData();
      data.set('llm_model', val);
      data.set('provider', currentProvider);
      try {
        const response = await fetch('/lmstudio/load', {method: 'POST', body: data, signal});
        window.location.href = response.url;
      } catch (error) {
        if (error.name !== 'AbortError') window.location.href = '/?error=' + encodeURIComponent(tr('model_failed'));
      }
    };

    if (modelInput) {
      const isEn = (document.documentElement.lang || 'en').startsWith('en');
      loadButton = document.createElement('button');
      loadButton.type = 'button';
      loadButton.className = 'load-model';
      loadButton.textContent = tr('model_select');
      modelInput.insertAdjacentElement('afterend', loadButton);

      loadButton.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        doLoadModel();
      });

      modelInput.addEventListener('change', () => {
        const p = provider ? provider.value : 'llamacpp';
        if (isLocalLoadProvider(p)) {
          updateLoadButtonState();

        }
      });
    }

    const applyProviderUI = () => {
      const p = provider.value;
      document.querySelectorAll('.custom-field').forEach(field => field.hidden = p !== 'custom');
      document.querySelector('.other-model-field').hidden = !(p === 'ollama' || p === 'custom');
      const modelField = document.querySelector('.lm-model-field');
      if (modelField) modelField.hidden = !isModelSelectProvider(p);
      applyProviderModelFilter(p);

      const useAiBox = form.querySelector('input[name="use_ai"]');
      const aiOn = useAiBox ? useAiBox.checked : true;
      const customModelInput = document.querySelector('[name="custom_model"]');
      if (customModelInput) {
        customModelInput.required = aiOn && (p === 'ollama' || p === 'custom');
      }
      const hasVisibleOption = modelSelectEl && [...modelSelectEl.options].some(o => !o.hidden && o.value);
      if (modelSelectEl) {
        modelSelectEl.required = aiOn && isModelSelectProvider(p) && hasVisibleOption;
      }
      
      const canLoad = isLocalLoadProvider(p);
      if (loadButton) {
        loadButton.hidden = !canLoad;
      }
      if (canLoad) {
        updateLoadButtonState();
      }
    };

    form.addEventListener('recipe-model-selected', () => {
      modelSelectEl?.querySelectorAll('option[data-provider]').forEach(option => {
        if (option.dataset.provider === provider.value) option.dataset.active = option.value === modelSelectEl.value ? 'true' : 'false';
      });
      updateLoadButtonState();
    });

    provider?.addEventListener('change', applyProviderUI);
    form.querySelector('input[name="use_ai"]')?.addEventListener('change', applyProviderUI);
    if (provider) applyProviderUI();

    const startProcessing = (title = tr('processing_title'), subtitle = tr('processing_subtitle')) => {
      controller = new AbortController();
      overlay.querySelector('h2').textContent = title;
      const subtitleEl = overlay.querySelector('h2 + p');
      subtitleEl.textContent = subtitle;
      overlay.hidden = false;
      const isDefaultImport = (title === tr('processing_title'));
      const started = Date.now();
      const tick = () => {
        const seconds = Math.floor((Date.now() - started) / 1000);
        elapsed.textContent = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
        if (isDefaultImport && subtitleEl) {
          const isEn = (document.documentElement.lang || 'en').startsWith('en');
          if (seconds >= 20) {
            subtitleEl.textContent = isEn ? 'Structuring ingredients & instructions… almost ready!' : 'Modell strukturiert Zutaten & Zubereitung... fast fertig!';
          } else if (seconds >= 8) {
            subtitleEl.textContent = tr('processing_model');
          } else {
            subtitleEl.textContent = subtitle;
          }
        }
      };
      tick(); timer = setInterval(tick, 1000);
      return controller.signal;
    };

    // --- Tabs Logic ---
    const container = document.querySelector('#import-container');
    const switchTab = (tabId) => {
      document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabId);
      });
      document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.toggle('active', content.id === tabId);
      });
      if (input) {
        input.required = (tabId === 'tab-import-url');
      }
    };

    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        switchTab(btn.dataset.tab);
      });
    });

    const extractUrl = event => {
      const raw = event.dataTransfer.getData('text/uri-list') || event.dataTransfer.getData('text/plain');
      return raw.split(/\r?\n/).map(x => x.trim()).find(x => /^https?:\/\//i.test(x));
    };
    if (container) {
      ['dragenter','dragover'].forEach(name => container.addEventListener(name,event => {event.preventDefault();container.classList.add('drag-active')}));
      ['dragleave','drop'].forEach(name => container.addEventListener(name,event => {event.preventDefault();container.classList.remove('drag-active')}));
      container.addEventListener('drop', event => {const url=extractUrl(event);if(url){input.value=url;switchTab('tab-import-url');input.focus()}});
    } else {
      ['dragenter','dragover'].forEach(name => form.addEventListener(name,event => {event.preventDefault();form.classList.add('drag-active')}));
      ['dragleave','drop'].forEach(name => form.addEventListener(name,event => {event.preventDefault();form.classList.remove('drag-active')}));
      form.addEventListener('drop', event => {const url=extractUrl(event);if(url){input.value=url;input.focus()}});
    }

    // --- Video Search Logic ---
    const videoSearchQuery = document.querySelector('#video-search-query');
    const videoSearchBtn = document.querySelector('#video-search-btn');
    const videoSearchResults = document.querySelector('#video-search-results');

    const performVideoSearch = async () => {
      if (!videoSearchQuery || !videoSearchResults) return;
      const q = videoSearchQuery.value.trim();
      if (!q) return;

      videoSearchResults.innerHTML = `
        <div class="video-search-loading">
          <div class="video-spinner"></div>
          <span>Video-Suche wird ausgeführt...</span>
        </div>
      `;

      try {
        const response = await fetch(`/api/youtube/search?q=${encodeURIComponent(q)}`);
        if (!response.ok) throw new Error(`Search failed: ${response.status}`);
        const data = await response.json();
        
        if (data.length === 0) {
          videoSearchResults.innerHTML = '<div class="video-no-results">Keine Rezepte gefunden.</div>';
          return;
        }

        videoSearchResults.innerHTML = '';
        data.forEach(item => {
          const card = document.createElement('div');
          card.className = 'video-result-card';
          card.setAttribute('role', 'button');
          card.setAttribute('tabindex', '0');
          card.innerHTML = `
            <div class="video-thumb-wrapper">
              <img src="${esc(item.thumbnail || '')}" class="video-thumb" alt="Thumbnail" onerror="this.style.display='none'">
              ${item.duration ? `<span class="video-duration">${esc(item.duration)}</span>` : ''}
            </div>
            <div class="video-info">
              <div class="video-title" title="${esc(item.title)}">${esc(item.title)}</div>
              <div class="video-channel">${esc(item.channel)}</div>
            </div>
            <button type="button" class="video-import-btn" data-url="${esc(item.url)}">Importieren</button>
          `;
          
          let importing = false;
          const triggerImport = () => {
            if (importing) return;
            importing = true;
            if (input) {
              input.value = item.url;
            }
            const btn = card.querySelector('.video-import-btn');
            if (btn) {
              btn.textContent = 'Importiere...';
              btn.disabled = true;
            }
            card.style.opacity = '0.6';
            form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
          };

          card.addEventListener('click', () => {
            triggerImport();
          });
          card.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              triggerImport();
            }
          });

          videoSearchResults.appendChild(card);
        });
      } catch (err) {
        console.error("Video search error:", err);
        videoSearchResults.innerHTML = '<div class="video-no-results">Fehler bei der Suche. Bitte versuche es erneut.</div>';
      }
    };

    if (videoSearchBtn) {
      videoSearchBtn.addEventListener('click', performVideoSearch);
    }
    if (videoSearchQuery) {
      videoSearchQuery.addEventListener('keypress', event => {
        if (event.key === 'Enter') {
          event.preventDefault();
          performVideoSearch();
        }
      });
    }

    form.addEventListener('submit', async event => {
      event.preventDefault();
      const signal = startProcessing();
      try {
        // Checkbox ist nur im gecheckten Zustand Teil des Formulars – Wert explizit senden.
        const fd = new FormData(form);
        const useAiCheckbox = form.querySelector('input[name="use_ai"]');
        fd.set('use_ai', useAiCheckbox && useAiCheckbox.checked ? 'true' : 'false');
        if (input && input.value) {
          fd.set('url', input.value);
        }
        const response = await fetch('/import', {method:'POST', body:fd, signal});
        window.location.href = response.url;
      } catch (error) {
        if (error.name !== 'AbortError') window.location.href = '/?error=Importverbindung+fehlgeschlagen';
      }
    });
  }
  // --- Favorite Toggle on Card Overlay ---
  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('.favorite-btn');
    if (!btn) return;
    
    e.preventDefault();
    e.stopPropagation();
    
    const recipeId = btn.dataset.id;
    try {
      const response = await fetch(`/recipe/${recipeId}/favorite`, {
        method: 'POST',
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      });
      if (response.ok) {
        const data = await response.json();
        btn.classList.toggle('is-favorite', data.favorite);
        const iconSpan = btn.querySelector('.heart-icon');
        if (iconSpan) {
          iconSpan.textContent = data.favorite ? '♥' : '♡';
        }
        
        const favoritesInput = document.querySelector('#favorites-input');
        if (favoritesInput && favoritesInput.value === '1') {
          const filtersForm = document.querySelector('.filters');
          if (filtersForm) {
            const formData = new FormData(filtersForm);
            const urlParams = new URLSearchParams(formData);
            if (window.updateRecipesGlobal) {
              window.updateRecipesGlobal(urlParams);
            }
          }
        }
      } else {
        alert("Server meldet Fehler beim Favorisieren: Status " + response.status);
      }
    } catch (err) {
      console.error("Failed to toggle favorite:", err);
      alert("Fehler beim Favorisieren (Karte): " + err.message);
    }
  });

  // --- Favorite Toggle on Details Page ---
  const favHeaderBtn = document.querySelector('#favorite-header-btn');

  if (favHeaderBtn) {
    favHeaderBtn.addEventListener('click', async () => {
      const recipeId = favHeaderBtn.dataset.id;
      try {
        const response = await fetch(`/recipe/${recipeId}/favorite`, {
          method: 'POST',
          headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });
        if (response.ok) {
          const data = await response.json();
          favHeaderBtn.classList.toggle('is-favorite', data.favorite);
          const iconSpan = favHeaderBtn.querySelector('.heart-icon');
          if (iconSpan) {
            iconSpan.textContent = data.favorite ? '♥' : '♡';
          }
        } else {
          alert("Server meldet Fehler beim Favorisieren: Status " + response.status);
        }
      } catch (err) {
        console.error("Failed to toggle favorite detail:", err);
        alert("Fehler beim Favorisieren (Header): " + err.message);
      }
    });
  }
})();
