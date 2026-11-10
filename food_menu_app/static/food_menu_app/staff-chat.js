(() => {
    const transcript = document.getElementById('staff-chat-transcript');
    if (!transcript) return;

    const status = document.getElementById('staff-chat-status');
    let lastMessageId = Number(transcript.dataset.lastId) || 0;
    let errorCount = 0;

    async function poll() {
        let nextInterval = 2500; // Default 2.5 seconds

        try {
            const response = await fetch(
                `${transcript.dataset.messagesUrl}?after=${lastMessageId}`,
                { credentials: 'same-origin' },
            );
            
            // Try parsing JSON safely even if server returns HTML error page
            let data;
            const contentType = response.headers.get("content-type");
            if (contentType && contentType.includes("application/json")) {
                data = await response.json();
            } else {
                throw new Error(`Server error (Status: ${response.status})`);
            }

            if (!response.ok) throw new Error(data.error || 'Could not refresh chat.');

            // Reset error count on success
            errorCount = 0;
            status.textContent = 'Chat connected. New customer messages appear here automatically.';

            for (const message of data.messages) {
                if (message.id <= lastMessageId) continue;

                const item = document.createElement('li');
                const sender = document.createElement('p');
                const content = document.createElement('p');
                item.className = message.sender === 'visitor'
                    ? 'mr-10 rounded-xl bg-amber-100 p-3'
                    : message.sender === 'admin'
                        ? 'ml-10 rounded-xl bg-emerald-100 p-3'
                        : 'mr-10 rounded-xl bg-stone-100 p-3';
                sender.className = 'text-xs font-bold uppercase text-stone-600';
                sender.textContent = message.sender === 'visitor'
                    ? 'Visitor'
                    : message.sender === 'admin' ? 'Staff' : 'Chatbot';
                content.className = 'mt-1 whitespace-pre-wrap text-sm text-stone-800';
                content.textContent = message.message;
                item.append(sender, content);
                item.dataset.messageId = message.id;
                transcript.appendChild(item);
                lastMessageId = message.id;
            }
            if (data.messages.length) transcript.scrollTop = transcript.scrollHeight;

        } catch (error) {
            errorCount++;
            console.warn(`Chat polling attempt failed (${errorCount}):`, error.message);
            status.textContent = 'Connection lost. Reconnecting...';

            // Exponential backoff: increase delay with each failure, cap it at 15 seconds
            nextInterval = Math.min(2500 * Math.pow(1.5, errorCount), 15000);
        } finally {
            window.setTimeout(poll, nextInterval);
        }
    }

    window.setTimeout(poll, 2500);
})();















// (() => {
//     const transcript = document.getElementById('staff-chat-transcript');
//     if (!transcript) return;

//     const status = document.getElementById('staff-chat-status');
//     let lastMessageId = Number(transcript.dataset.lastId) || 0;

//     async function poll() {
//         try {
//             const response = await fetch(
//                 `${transcript.dataset.messagesUrl}?after=${lastMessageId}`,
//                 { credentials: 'same-origin' },
//             );
//             const data = await response.json();
//             if (!response.ok) throw new Error(data.error || 'Could not refresh chat.');

//             for (const message of data.messages) {
//                 if (message.id <= lastMessageId) continue;

//                 const item = document.createElement('li');
//                 const header = document.createElement('div');
//                 const avatar = document.createElement('span');
//                 const sender = document.createElement('p');
//                 const content = document.createElement('p');
//                 header.className = 'mb-2 flex items-center gap-2';
//                 item.className = message.sender === 'visitor'
//                     ? 'mr-10 rounded-xl bg-amber-100 p-3'
//                     : message.sender === 'admin'
//                         ? 'ml-10 rounded-xl bg-emerald-100 p-3'
//                         : 'mr-10 rounded-xl bg-stone-100 p-3';
//                 avatar.className = 'flex h-8 w-8 shrink-0 items-center justify-center overflow-hidden rounded-full bg-white text-xs font-bold text-emerald-900';
//                 if (message.avatar_url) {
//                     const image = document.createElement('img');
//                     image.src = message.avatar_url;
//                     image.alt = '';
//                     image.className = 'h-full w-full object-cover';
//                     avatar.appendChild(image);
//                 } else {
//                     avatar.textContent = (message.sender_name || '?').slice(0, 1).toUpperCase();
//                 }
//                 sender.className = 'text-xs font-bold text-stone-700';
//                 sender.textContent = message.sender_name || 'Chat';
//                 content.className = 'mt-1 whitespace-pre-wrap text-sm text-stone-800';
//                 content.textContent = message.message;
//                 header.append(avatar, sender);
//                 item.append(header, content);
//                 item.dataset.messageId = message.id;
//                 transcript.appendChild(item);
//                 lastMessageId = message.id;
//             }
//             if (data.messages.length) transcript.scrollTop = transcript.scrollHeight;
//             status.textContent = 'Chat connected. New customer messages appear here automatically.';
//         } catch (error) {
//             status.textContent = error.message;
//         } finally {
//             window.setTimeout(poll, 2500);
//         }
//     }

//     window.setTimeout(poll, 2500);
// })();
