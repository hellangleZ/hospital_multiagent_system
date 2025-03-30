/**
 * 医院智能问诊系统 - 前端交互脚本
 * 最终完整版本 - 清晰结构 v14 (Final escapeHtml Fix)
 */

console.log("app.js: Final Clear Version v14 (Final escapeHtml Fix) - Script loaded.");

document.addEventListener('DOMContentLoaded', () => {
    console.log("app.js: Final Clear Version v14 - DOMContentLoaded event fired.");

    try {
        // --- Get DOM Elements ---
        const consultationDialog = document.getElementById('consultationDialog');
        const dialogContent = document.getElementById('dialogContent');
        const dialogInput = document.getElementById('dialogInput');
        const patientResponse = document.getElementById('patientResponse');
        const submitResponse = document.getElementById('submitResponse');
        const diagnosisResultDiv = document.getElementById('diagnosisResult');
        let diagnosisContent = null;
        const interactionLogArea = document.getElementById('interactionLog');

        if (!consultationDialog || !dialogContent || !dialogInput || !patientResponse || !submitResponse || !diagnosisResultDiv || !interactionLogArea) {
            console.error("app.js: CRITICAL ERROR - Essential HTML elements not found!");
            throw new Error("页面初始化失败：缺少必要的HTML元素。");
        } else {
            console.log("app.js: Base elements and interaction log area found.");
            diagnosisContent = diagnosisResultDiv.querySelector('.result-content');
            if (!diagnosisContent) { console.error("app.js: CRITICAL ERROR - '.result-content' child missing!"); }
            else { console.log("app.js: Diagnosis result content area found."); }
        }

        // --- State Variables ---
        let currentConsultationId = null;
        let isConsultationActive = false;

        // --- Helper Functions ---

        function initAutoResize(textarea) { /* ... (same) ... */
            let dt; function pr(){try{textarea.style.height='auto';textarea.style.height=(textarea.scrollHeight+2)+'px'}catch(e){console.error("AR:",e)}} function dr(){clearTimeout(dt);dt=setTimeout(pr,50)} textarea.addEventListener('input',dr);textarea.addEventListener('focus',pr);setTimeout(pr,50); console.debug("AR init.");
         }

        // --- escapeHtml function with ROBUST error checking ---
        function escapeHtml(unsafe) {
            try {
                // First, log what we received for debugging
                console.debug(`escapeHtml received: type=${typeof unsafe}, value=`, unsafe);
                
                // Handle null or undefined
                if (unsafe === null || unsafe === undefined) {
                    console.warn("escapeHtml: Received null or undefined value");
                    return '';
                }
                
                // Convert to string safely
                let safeString;
                try {
                    safeString = String(unsafe);
                } catch (e) {
                    console.error("escapeHtml: Failed to convert to string:", e);
                    return ''; // Return empty string on conversion failure
                }
                
                // Double check that we have a valid string before running replace operations
                if (typeof safeString !== 'string') {
                    console.error("escapeHtml: Failed to get string after conversion, type=", typeof safeString);
                    return '';
                }
                
                // Now safely perform the replacements
                try {
                    return safeString
                        .replace(/&/g, "&amp;")
                        .replace(/</g, "&lt;")
                        .replace(/>/g, "&gt;")
                        .replace(/"/g, "&quot;")
                        .replace(/'/g, "&#039;");
                } catch (e) {
                    console.error("escapeHtml: Error during string replacements:", e);
                    // Last resort: return the input if we can, or empty string
                    return typeof safeString === 'string' ? safeString : '';
                }
            } catch (e) {
                console.error("escapeHtml: Critical error:", e);
                return ''; // Return empty string on any failure
            }
        }
        // --- End escapeHtml function ---


        function appendMessage(role, message, isLoading = false) {
            console.debug(`Appending: R=${role}, L=${isLoading}, M=${typeof message === 'string' ? message.substring(0, 70) : 'non-string'}...`);
            
            if (!dialogContent) {
                console.error("No dialogContent.");
                return;
            }
            
            try {
                // Create message elements
                const wrapper = document.createElement("div");
                wrapper.className = `message ${role}-message`;
                
                const avatar = document.createElement("div");
                avatar.className = "message-avatar";
                
                // Safe avatar mapping
                const iconMap = {
                    receptionist: "R",
                    patient: "P",
                    doctor: "D",
                    pharmacist: "Ph",
                    system: "S"
                };
                avatar.textContent = iconMap[role] || "?";
                
                const content = document.createElement("div");
                content.className = "message-content";
                
                // Process message content safely
                if (isLoading) {
                    // Loading indicator plus escaped message
                    content.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${escapeHtml(message)}`;
                } else {
                    // Regular message with newlines converted to <br> tags
                    try {
                        // Use our enhanced escapeHtml function which already handles null/undefined
                        const escapedHtml = escapeHtml(message);
                        
                        // Now safely try to replace newlines
                        let htmlWithLineBreaks;
                        try {
                            htmlWithLineBreaks = escapedHtml.replace(/\n/g, "<br>");
                        } catch (replaceErr) {
                            console.error("Failed to replace newlines:", replaceErr);
                            htmlWithLineBreaks = escapedHtml;
                        }
                        
                        content.innerHTML = htmlWithLineBreaks;
                    } catch (contentErr) {
                        console.error("Failed to process message content:", contentErr);
                        content.textContent = "[无法显示消息内容]";
                    }
                }
                
                // Build and append the message
                wrapper.appendChild(avatar);
                wrapper.appendChild(content);
                dialogContent.appendChild(wrapper);
                
                // Scroll to the new message
                dialogContent.scrollTo({
                    top: dialogContent.scrollHeight,
                    behavior: "smooth"
                });
            } catch (e) {
                console.error("AppendMsg err:", e);
            }
        }

        function removeLastMessage() { /* ... (same) ... */
            if(!dialogContent)return;try{const l=dialogContent.lastElementChild;if(l&&l.classList.contains("system-message")&&l.querySelector(".fa-spinner")){dialogContent.removeChild(l);console.debug("Removed loading.")}}catch(e){console.error("RemoveMsg err:",e)}
        }

        function clearResultsArea() { /* ... (same) ... */
            if(diagnosisContent){diagnosisContent.innerHTML=''} if(diagnosisResultDiv){diagnosisResultDiv.classList.add('hidden')} console.debug("Cleared results.")
        }

        function displayDiagnosisInfo(diagnosisInfo) {
            console.log("Displaying diagnosis:", diagnosisInfo);
            
            // Check for required elements and valid input
            if (!diagnosisContent || !diagnosisResultDiv) {
                console.error("Cannot display diagnosis: Missing DOM elements");
                return;
            }
            
            if (!diagnosisInfo || typeof diagnosisInfo !== 'object' || !diagnosisInfo.condition) {
                console.warn("Invalid diagnosis info:", diagnosisInfo);
                return;
            }
            
            try {
                // Clear previous content
                clearResultsArea();
                
                // Start building HTML content with safe escaping
                let h = `<h4>诊断信息</h4>`;
                
                // Add diagnosis condition (required)
                const safeCondition = escapeHtml(diagnosisInfo.condition);
                h += `<p><strong>诊断结果:</strong> ${safeCondition}</p>`;
                
                // Add severity if available
                if (diagnosisInfo.severity) {
                    const safeSeverity = escapeHtml(diagnosisInfo.severity);
                    h += `<p><strong>严重程度:</strong> ${safeSeverity}</p>`;
                }
                
                // Add explanation if available - with safe newline replacement
                if (diagnosisInfo.explanation) {
                    try {
                        const safeExplanation = escapeHtml(diagnosisInfo.explanation);
                        const explanationWithBreaks = safeExplanation.replace(/\n/g, "<br>");
                        h += `<p><strong>说明:</strong> ${explanationWithBreaks}</p>`;
                    } catch (explErr) {
                        console.error("Error processing explanation:", explErr);
                        h += `<p><strong>说明:</strong> ${escapeHtml(String(diagnosisInfo.explanation))}</p>`;
                    }
                }
                
                // Add diagnostic tests if available
                if (diagnosisInfo.diagnostic_tests && 
                    Array.isArray(diagnosisInfo.diagnostic_tests) && 
                    diagnosisInfo.diagnostic_tests.length > 0) {
                    
                    try {
                        // Map each test to a safe string representation
                        const testStrings = diagnosisInfo.diagnostic_tests.map((test, index) => {
                            try {
                                if (typeof test === 'string') {
                                    return escapeHtml(test);
                                } else if (typeof test === 'object' && test !== null) {
                                    const testName = test.name || test.test_name || test.test;
                                    if (testName) {
                                        return escapeHtml(testName);
                                    } else {
                                        try {
                                            return escapeHtml(JSON.stringify(test));
                                        } catch (jsonErr) {
                                            console.warn(`Failed to stringify test[${index}]:`, jsonErr);
                                            return '[对象]';
                                        }
                                    }
                                } else {
                                    return escapeHtml(String(test));
                                }
                            } catch (testErr) {
                                console.error(`Error processing test[${index}]:`, testErr);
                                return '[处理错误]';
                            }
                        });
                        
                        // Join the test strings safely
                        h += `<p><strong>建议检查:</strong> ${testStrings.join(", ")}</p>`;
                    } catch (testsErr) {
                        console.error("Error processing diagnostic tests:", testsErr);
                        h += `<p><strong>建议检查:</strong> [无法显示检查项]</p>`;
                    }
                }
                
                // Update DOM
                diagnosisContent.innerHTML = h;
                diagnosisResultDiv.classList.remove('hidden');
                console.debug("Displayed diagnosis successfully");
                
                // Scroll to make visible
                diagnosisResultDiv.scrollIntoView({behavior: "smooth", block: "start"});
                
            } catch (e) {
                console.error("Error displaying diagnosis info:", e);
                try {
                    // Fallback display in case of error
                    diagnosisContent.innerHTML = 
                        `<h4>诊断信息</h4>
                        <p><strong>诊断结果:</strong> ${escapeHtml(diagnosisInfo.condition || '未知')}</p>
                        <p><em>注意: 部分诊断信息显示失败</em></p>`;
                    diagnosisResultDiv.classList.remove('hidden');
                } catch (fallbackErr) {
                    console.error("Even fallback display failed:", fallbackErr);
                }
            }
        }

        function displayPrescription(prescription) {
            console.log("Displaying prescription:", prescription);
            
            // Check for required elements and valid input
            if (!diagnosisContent || !diagnosisResultDiv) {
                console.error("Cannot display prescription: Missing DOM elements");
                return;
            }
            
            // Check for valid prescription data
            let hasValidMedications = false;
            if (prescription && 
                typeof prescription === 'object' && 
                Array.isArray(prescription.medications) && 
                prescription.medications.length > 0) {
                
                // Check that at least one medication has a name
                hasValidMedications = prescription.medications.some(m => 
                    m && typeof m === 'object' && m.name);
            }
            
            // If no valid medications, show a message if appropriate
            if (!hasValidMedications) {
                console.info("No valid medications in prescription");
                
                // Only add "No prescription" message if we're displaying a diagnosis and don't already have this message
                if (!diagnosisResultDiv.classList.contains('hidden') && 
                    !diagnosisContent.querySelector('.prescription-details')) {
                    
                    if (!diagnosisContent.textContent.includes("无需药物处方") && 
                        !diagnosisContent.textContent.includes("未开具有效药物处方")) {
                        
                        diagnosisContent.innerHTML += `<p>未开具有效药物处方。</p>`;
                    }
                }
                return;
            }
            
            try {
                // Start building prescription HTML
                let h = '';
                
                // Determine if we need headers
                const needsHeader = diagnosisResultDiv.classList.contains('hidden') || 
                                 !diagnosisContent.querySelector('.prescription-details');
                
                // If diagnosis area is hidden, clear it first
                if (diagnosisResultDiv.classList.contains('hidden')) {
                    clearResultsArea();
                }
                
                // Add header if needed
                if (needsHeader) {
                    h += `<hr><h4>处方信息</h4>`;
                }
                
                // Start prescription details section
                h += `<div class="prescription-details">
                      <div class="medications">
                      <h5>药品清单：</h5><ul>`;
                
                // Add medications
                prescription.medications.forEach((m, index) => {
                    try {
                        if (m && typeof m === 'object' && m.name) {
                            const medName = escapeHtml(m.name);
                            const dosage = escapeHtml(m.dosage || '遵医嘱');
                            const frequency = escapeHtml(m.frequency || '遵医嘱');
                            h += `<li><strong>${medName}</strong>: ${dosage}, ${frequency}</li>`;
                        } else {
                            console.warn(`Invalid medication at index ${index}:`, m);
                        }
                    } catch (medErr) {
                        console.error(`Error processing medication[${index}]:`, medErr);
                    }
                });
                
                h += `</ul></div>`;
                
                // Add instructions if available
                try {
                    const instructions = Array.isArray(prescription.instructions) ? 
                        prescription.instructions.join('\n') : 
                        prescription.instructions;
                        
                    if (typeof instructions === 'string' && instructions.trim()) {
                        const safeInstructions = escapeHtml(instructions);
                        // Safely replace newlines with <br>
                        let instructionsWithBreaks;
                        try {
                            instructionsWithBreaks = safeInstructions.replace(/\n/g, "<br>");
                        } catch (replaceErr) {
                            console.warn("Failed to replace newlines in instructions:", replaceErr);
                            instructionsWithBreaks = safeInstructions;
                        }
                        h += `<div class="instructions">
                             <h5>用药说明/建议：</h5>
                             <p>${instructionsWithBreaks}</p>
                             </div>`;
                    }
                } catch (instrErr) {
                    console.error("Error processing instructions:", instrErr);
                }
                
                // Add notes if available
                try {
                    const notes = prescription.notes;
                    if (typeof notes === 'string' && notes.trim()) {
                        const safeNotes = escapeHtml(notes);
                        // Safely replace newlines with <br>
                        let notesWithBreaks;
                        try {
                            notesWithBreaks = safeNotes.replace(/\n/g, "<br>");
                        } catch (replaceErr) {
                            console.warn("Failed to replace newlines in notes:", replaceErr);
                            notesWithBreaks = safeNotes;
                        }
                        h += `<div class="notes">
                             <h5>注意事项/随访：</h5>
                             <p>${notesWithBreaks}</p>
                             </div>`;
                    }
                } catch (notesErr) {
                    console.error("Error processing notes:", notesErr);
                }
                
                // Add pharmacist notes if available
                try {
                    const pharmNotes = prescription.pharmacist_notes;
                    if (typeof pharmNotes === 'string' && pharmNotes.trim()) {
                        const safePharmNotes = escapeHtml(pharmNotes);
                        // Safely replace newlines with <br>
                        let pharmNotesWithBreaks;
                        try {
                            pharmNotesWithBreaks = safePharmNotes.replace(/\n/g, "<br>");
                        } catch (replaceErr) {
                            console.warn("Failed to replace newlines in pharmacist notes:", replaceErr);
                            pharmNotesWithBreaks = safePharmNotes;
                        }
                        h += `<div class="notes">
                             <h5>药剂师建议：</h5>
                             <p>${pharmNotesWithBreaks}</p>
                             </div>`;
                    }
                } catch (pharmNotesErr) {
                    console.error("Error processing pharmacist notes:", pharmNotesErr);
                }
                
                // Close prescription details
                h += `</div>`;
                
                // Remove existing prescription if any
                const existingPrescription = diagnosisContent.querySelector('.prescription-details');
                if (existingPrescription) {
                    existingPrescription.remove();
                    console.debug("Removed existing prescription details");
                }
                
                // Remove any "no prescription" messages
                const noPrescriptionMsg = Array.from(diagnosisContent.querySelectorAll('p'))
                    .find(p => p.textContent.includes("无需药物处方") || 
                               p.textContent.includes("未开具有效药物处方"));
                if (noPrescriptionMsg) {
                    noPrescriptionMsg.remove();
                }
                
                // Add the new prescription to the content
                diagnosisContent.innerHTML += h;
                diagnosisResultDiv.classList.remove('hidden');
                console.debug("Displayed prescription successfully");
                
                // Scroll to view
                diagnosisResultDiv.scrollIntoView({behavior: 'smooth', block: 'end'});
                
            } catch (e) {
                console.error("Error displaying prescription:", e);
                try {
                    // Fallback display in case of error
                    if (!diagnosisResultDiv.classList.contains('hidden')) {
                        diagnosisContent.innerHTML += 
                            `<p><strong>处方信息：</strong> 处方信息显示失败，但您可以询问医生或药剂师获取详情。</p>`;
                    }
                } catch (fallbackErr) {
                    console.error("Even fallback prescription display failed:", fallbackErr);
                }
            }
        }

        function setInputEnabled(enabled) { /* ... (same) ... */
             if(!patientResponse||!submitResponse||!dialogInput){console.error("setInputEnabled failed.");return} patientResponse.disabled=!enabled;submitResponse.disabled=!enabled;dialogInput.classList.toggle("disabled",!enabled); if(enabled){patientResponse.placeholder="请输入您想咨询的内容...";patientResponse.style.minHeight='';try{setTimeout(()=>{patientResponse.dispatchEvent(new Event('input'))},0)}catch(e){console.error("Resize err:",e)}console.log(`Input ENABLED.`)}else{patientResponse.placeholder="请等待回复或咨询已结束...";try{patientResponse.style.height='auto';patientResponse.style.minHeight='initial';console.log("Height reset.")}catch(e){console.error("Reset height err:",e)}console.log(`Input DISABLED.`)}
        }

        function displayInteractionEvents(events) {
            if (!interactionLogArea) return;
            
            console.debug("Processing interaction events:", events);
            
            // Handle invalid events array
            if (!events || !Array.isArray(events)) {
                interactionLogArea.innerHTML = '<p><i>无法加载日志。</i></p>';
                return;
            }
            
            // Handle empty events array
            if (events.length === 0) {
                interactionLogArea.innerHTML = '<p><i>暂无记录。</i></p>';
                return;
            }
            
            // Filter out unwanted "System → 错误" messages
            const filteredEvents = events.filter(event => {
                // Skip events that are System errors without specific details
                if (event && 
                    event.source === "System" && 
                    event.action === "错误" && 
                    (!event.details || !event.details.message || event.details.message === "")) {
                    console.debug("Filtering out generic System error event:", event);
                    return false;
                }
                return true;
            });
            
            // If all events were filtered out
            if (filteredEvents.length === 0) {
                interactionLogArea.innerHTML = '<p><i>暂无有效记录。</i></p>';
                return;
            }
            
            let h = '<ul class="interaction-log-list">';
            
            try {
                filteredEvents.forEach((e, index) => {
                    try {
                        // Safe access of timestamp
                        const timestamp = (e && e.timestamp) ? e.timestamp : '??:??:??';
                        // Process timestamp safely
                        let timeStr = '??:??:??';
                        try {
                            if (typeof timestamp === 'string' && timestamp.includes('T')) {
                                timeStr = timestamp.split('T')[1].replace('Z', '');
                            } else if (typeof timestamp === 'string') {
                                timeStr = timestamp;
                            } else {
                                timeStr = String(timestamp);
                            }
                        } catch (timeErr) {
                            console.warn(`Event[${index}]: Failed to parse timestamp:`, timeErr);
                        }
                        
                        // Safe access of other fields
                        const source = (e && typeof e.source !== 'undefined') ? e.source : 'Unk';
                        const target = (e && typeof e.target !== 'undefined') ? e.target : 'Unk';
                        const action = (e && typeof e.action !== 'undefined') ? e.action : 'Unk Action';
                        
                        // Get human readable description if available
                        let humanReadable = '';
                        if (e && e.human_readable && typeof e.human_readable === 'string') {
                            humanReadable = e.human_readable;
                        }
                        
                        // Format details safely
                        let detailsString = '';
                        
                        if (e && e.details && typeof e.details === 'object') {
                            // New approach: Show status description if available
                            if (e.details.status_description) {
                                detailsString += `${escapeHtml(e.details.status_description)}`;
                            } else if (e.details.status) {
                                detailsString += `状态: ${escapeHtml(e.details.status)}`;
                            } else if (e.details.error) {
                                const errorText = typeof e.details.error === 'string' ? 
                                    e.details.error : 
                                    (e.details.error instanceof Error ? 
                                        e.details.error.message : 
                                        String(e.details.error));
                                detailsString += `错误: ${escapeHtml(errorText.substring(0, 100))}...`;
                            } else if (e.details.message_snippet) {
                                detailsString += `${escapeHtml(e.details.message_snippet)}`;
                            } else if (e.details.request_type) {
                                detailsString += `请求类型: ${escapeHtml(e.details.request_type)}`;
                            } else {
                                try {
                                    const detailsJson = JSON.stringify(e.details);
                                    if (detailsJson && detailsJson !== '{}') {
                                        detailsString = escapeHtml(detailsJson.substring(0, 80));
                                        if (detailsJson.length > 80) detailsString += '...';
                                    }
                                } catch (jsonErr) {
                                    detailsString = '[details]';
                                    console.warn(`Event[${index}]: Failed to stringify details:`, jsonErr);
                                }
                            }
                        }
                        
                        // Use roles for CSS classes
                        const sourceClass = getAgentClass(source);
                        const targetClass = getAgentClass(target);
                        
                        // Build HTML with human readable description as the primary content
                        let eventDisplay;
                        if (humanReadable) {
                            // Primary display is human readable description
                            eventDisplay = escapeHtml(humanReadable);
                            
                            // Add details if available and not redundant
                            if (detailsString && !humanReadable.includes(detailsString)) {
                                eventDisplay += ` <span class="log-details">${detailsString}</span>`;
                            }
                        } else {
                            // Fallback to traditional format
                            eventDisplay = `<span class="log-source ${sourceClass}">${escapeHtml(source)}</span>→
                                <span class="log-target ${targetClass}">${escapeHtml(target)}</span>
                                <span class="log-action">${escapeHtml(action)}</span>`;
                            
                            if (detailsString) {
                                eventDisplay += ` <span class="log-details">${detailsString}</span>`;
                            }
                        }
                        
                        h += `<li>
                            <span class="log-timestamp">${escapeHtml(timeStr)}</span>
                            <span class="log-content">${eventDisplay}</span>
                        </li>`;
                    } catch (eventErr) {
                        console.error(`Error processing event[${index}]:`, eventErr, e);
                        // Add a fallback entry that won't break the display
                        h += '<li><span class="log-timestamp">??:??:??</span><span class="log-content">处理日志项时出错</span></li>';
                    }
                });
            } catch (eventsErr) {
                console.error("Failed to process events array:", eventsErr);
                h += '<li><span class="log-timestamp">??:??:??</span><span class="log-content">处理日志列表时出错</span></li>';
            }
            
            h += '</ul>';
            interactionLogArea.innerHTML = h;
            interactionLogArea.scrollTop = interactionLogArea.scrollHeight;
        }

        // Helper function to get CSS class for agent role
        function getAgentClass(role) {
            const roleMap = {
                'receptionist': 'role-receptionist',
                'doctor': 'role-doctor',
                'pharmacist': 'role-pharmacist',
                'system': 'role-system',
                'user': 'role-user',
                'User': 'role-user',
                'Orchestrator': 'role-system'
            };
            return roleMap[role] || 'role-unknown';
        }


        // --- Initialization and Event Listeners ---
        try { initAutoResize(patientResponse); } catch (e) { console.error("Failed initAutoResize:", e); }
        setInputEnabled(false);
        try { /* ... (keydown listener same) ... */
            patientResponse.addEventListener('keydown',(event)=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();if(!submitResponse.disabled){console.log("Enter, submit.");submitResponse.click()}else{console.log("Enter, disabled.")}}});console.log("Keydown listener added.");
        } catch (e) { console.error("Failed keydown listener:", e); }

        async function initReceptionist() { /* ... (same) ... */
            console.log("initR called.");isConsultationActive=false;setInputEnabled(false);clearResultsArea();appendMessage("system","连接中...",true);try{console.log("Fetching start...");const r=await fetch("/api/start_consultation",{method:"POST",headers:{"Content-Type":"application/json"}});console.log(`Start status: ${r.status}`);removeLastMessage();if(!r.ok){let m=`HTTP ${r.status}`;try{const d=await r.json();m=d.message||JSON.stringify(d)}catch(e){}throw new Error(`无法开始 (${m})`)}const d=await r.json();console.log("Start data:",d);if(d&&d.status==="success"&&d.initial_message&&typeof d.initial_message==='object'){currentConsultationId=d.consultation_id;console.log("Started, ID:",currentConsultationId);const a=d.initial_message.agent_type||"receptionist";const t=d.initial_message.message;if(typeof t==="string"&&t.trim()!==""){console.log("Appending initial from:",a);appendMessage(a,t);setInputEnabled(true);isConsultationActive=true;patientResponse.focus();console.log("Init successful.");displayInteractionEvents([])}else{console.error("Initial msg invalid:",d.initial_message);throw new Error("无效初始问候语。")}}else{console.error("Invalid start response:",d);throw new Error(d.message||"无效初始信息。")}}catch(e){console.error("init FAILED:",e);removeLastMessage();appendMessage("system",`初始化失败: ${escapeHtml(e.message||"未知错误")} 请刷新。`);setInputEnabled(false);isConsultationActive=false}
        }


        // --- Submit User Message ---
        try {
            console.log("Adding submit click listener.");
            submitResponse.addEventListener('click', async () => {
                console.log("Submit clicked.");
                if (!isConsultationActive) { console.log("Submit blocked: Inactive."); return; }
                const messageText = patientResponse.value.trim();
                if (!messageText) { console.log("Submit blocked: Empty msg."); return; }

                console.log("Sending message:", messageText);
                setInputEnabled(false);

                try {
                    appendMessage("patient", messageText);
                    patientResponse.value = "";
                    patientResponse.dispatchEvent(new Event("input"));
                    appendMessage("system", "正在处理...", true);

                    console.log("Fetching /api/conversation...");
                    const response = await fetch("/api/conversation", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ consultation_id: currentConsultationId, message: messageText })
                    });
                    console.log(`Conversation response status: ${response.status}`);
                    removeLastMessage();

                    if (!response.ok) { throw new Error(`发送消息失败 (HTTP ${response.status})`); }

                    const responseData = await response.json();
                    console.log("Received response:", responseData);

                    if (responseData && responseData.agent_type && responseData.message) {
                        appendMessage(responseData.agent_type, responseData.message);
                        if (responseData.diagnosis_info) { displayDiagnosisInfo(responseData.diagnosis_info); }
                        if (responseData.prescription) { displayPrescription(responseData.prescription); }
                        else if (responseData.status === 'completed_no_prescription') { /* ... no prescription msg ... */
                             if(diagnosisContent&&!diagnosisResultDiv.classList.contains('hidden')&&!diagnosisContent.querySelector('.prescription-details')){if(!diagnosisContent.textContent.includes("无需药物处方")){diagnosisContent.innerHTML+=`<p>本次诊断无需药物处方。</p>`}}
                         }
                        if (responseData.interaction_log) { displayInteractionEvents(responseData.interaction_log); }

                        const backendStatus = responseData.status || "in_progress";
                        const terminalStatuses = ["completed_no_prescription", "completed_prescription", "error_prescription_rejected", "error"];

                        if (terminalStatuses.includes(backendStatus)) { /* ... handle terminal states ... */
                           console.log(`Ended: ${backendStatus}`); isConsultationActive=false;setInputEnabled(false);patientResponse.placeholder="本次咨询已结束。"; let endMsg="咨询结束。"; if(backendStatus.startsWith("error")||backendStatus==="error_prescription_rejected"){endMsg="处理出错或处方未通过，咨询结束。"} if(!responseData.message.includes("咨询已结束")&&!responseData.message.includes("审核未通过")){appendMessage("system",endMsg)}
                        } else if (backendStatus === "prescription_pending" || backendStatus === "info_displayed") { /* ... handle specific intermediate states ... */
                           console.log(`Status ${backendStatus}. Input enabled.`); setInputEnabled(true); if(backendStatus==="prescription_pending"){patientResponse.placeholder="处方处理中..."} patientResponse.focus();
                        } else { /* ... handle default in_progress state ... */
                           console.log("In progress, enabling input."); setInputEnabled(true); patientResponse.focus();
                        }

                    } else { throw new Error("收到服务器返回的未知格式响应。"); }

                } catch (error) { // Catch block (robust handling from v12)
                    console.error("Error during submitResponse handler:", error);
                    removeLastMessage();
                    let displayErrorMessage = "未知错误";
                    if (error instanceof Error) { displayErrorMessage = error.message || "发生了一个错误"; }
                    else if (error) { try { displayErrorMessage = String(error); } catch (e) { displayErrorMessage = "无法解析的错误信息"; } }
                    if (typeof displayErrorMessage !== 'string') {
                        displayErrorMessage = "未知错误类型";
                    }
                    appendMessage("system", `通信错误: ${escapeHtml(displayErrorMessage)}。请检查网络并重试。`);
                    setInputEnabled(true);
                }
            });
            console.log("Click listener added successfully.");
        } catch (error) {
            console.error("Failed add click listener:", error);
            if (submitResponse) submitResponse.disabled = true;
            if (patientResponse) patientResponse.disabled = true;
            appendMessage('system', '无法初始化发送，请刷新。');
        }

        console.log("Calling initReceptionist() ...");
        initReceptionist();

    } catch (error) {
        console.error("GLOBAL ERROR:", error);
        try {
            const errorDisplay = document.getElementById('dialogContent') || document.body;
            if (errorDisplay) {
                errorDisplay.innerHTML = `
                    <div style="padding:20px;color:red;font-weight:bold;border:1px solid red;margin:10px;">
                        页面脚本初始化错误！<br>
                        错误: ${escapeHtml(error.message)}<br>
                        请检查控制台(F12)。
                    </div>`;
            } else {
                alert(`页面脚本初始化错误！\n${escapeHtml(error.message)}`);
            }
        } catch (displayError) {
            console.error("Error displaying global error:", displayError);
            alert(`页面脚本初始化错误！\n${escapeHtml(error.message)}`);
        }

        try {
            const patientInput = document.getElementById('patientResponse');
            const submitButton = document.getElementById('submitResponse');
            const dialogInput = document.getElementById('dialogInput');
            
            if (patientInput) patientInput.disabled = true;
            if (submitButton) submitButton.disabled = true;
            if (dialogInput) dialogInput.classList.add('disabled');
        } catch (disableError) {
            console.error("Error disabling inputs:", disableError);
        }
    }
}); // End DOMContentLoaded

console.log("app.js: Final Clear Version v14 (Final escapeHtml Fix) - Script finished loading.");