(() => {
    const widget = document.getElementById('chat-widget');
    if (!widget) return;

    const startForm = document.getElementById('chat-start-form');
    const messageForm = document.getElementById('chat-message-form');
    const transcript = document.getElementById('chat-transcript');
    const status = document.getElementById('chat-status');
    const minimizeButton = document.getElementById('chat-minimize');
    const csrfToken = widget.querySelector('[name=csrfmiddlewaretoken]').value;
    let lastMessageId = 0;
    let active = false;

    minimizeButton.addEventListener('click', () => {
        widget.open = false;
        widget.querySelector('summary').focus();
    });

    async function request(url, options = {}) {
        const response = await fetch(url, {
            credentials: 'same-origin',
            ...options,
            headers: {
                'X-CSRFToken': csrfToken,
                ...options.headers,
            },
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'The chat request could not be completed.');
        }
        return data;
    }

    function showMessages(messages) {
        for (const message of messages) {
            if (message.id <= lastMessageId) continue;

            const bubble = document.createElement('p');
            const header = document.createElement('div');
            const avatar = document.createElement('span');
            const sender = document.createElement('strong');
            sender.textContent = message.sender === 'visitor'
                ? (message.sender_name || 'You')
                : message.sender === 'admin'
                    ? (message.sender_name ? `@${message.sender_name}` : 'Our team')
                    : 'FoodMenu Assistant';
            header.className = 'mb-1 flex items-center gap-2';
            bubble.className = message.sender === 'visitor'
                ? 'ml-8 rounded-xl bg-emerald-100 p-3 text-sm'
                : 'mr-8 rounded-xl bg-stone-100 p-3 text-sm';
            avatar.className = 'flex h-7 w-7 shrink-0 items-center justify-center overflow-hidden rounded-full bg-white text-xs font-bold text-emerald-900';
            if (message.avatar_url) {
                const image = document.createElement('img');
                image.src = message.avatar_url;
                image.alt = '';
                image.className = 'h-full w-full object-cover';
                avatar.appendChild(image);
            } else {
                avatar.textContent = sender.textContent.slice(0, 1).toUpperCase();
            }
            const content = document.createElement('span');
            content.className = 'block whitespace-pre-wrap';
            content.textContent = message.message;
            header.append(avatar, sender);
            bubble.append(header, content);
            transcript.appendChild(bubble);
            lastMessageId = message.id;
        }
        if (messages.length) transcript.scrollTop = transcript.scrollHeight;
    }

    function showActiveChat(messages) {
        active = true;
        startForm.classList.add('hidden');
        messageForm.classList.remove('hidden');
        status.textContent = 'Our assistant replies instantly. Staff replies appear here too.';
        showMessages(messages);
        window.setTimeout(pollForMessages, 2500);
    }

    async function pollForMessages() {
        if (!active) return;
        try {
            const separator = widget.dataset.messagesUrl.includes('?') ? '&' : '?';
            const data = await request(
                `${widget.dataset.messagesUrl}${separator}after=${lastMessageId}`,
            );
            showMessages(data.messages);
            status.textContent = 'Chat connected. Our assistant and staff can reply here.';
        } catch (error) {
            status.textContent = error.message;
        } finally {
            if (active) window.setTimeout(pollForMessages, 2500);
        }
    }

    startForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        const button = startForm.querySelector('button[type=submit]');
        button.disabled = true;
        status.textContent = 'Connecting...';
        try {
            const data = await request(widget.dataset.startUrl, {
                method: 'POST',
                body: new FormData(startForm),
            });
            showActiveChat(data.messages);
        } catch (error) {
            status.textContent = error.message;
        } finally {
            button.disabled = false;
        }
    });

    messageForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        const button = messageForm.querySelector('button[type=submit]');
        button.disabled = true;
        try {
            const data = await request(widget.dataset.sendUrl, {
                method: 'POST',
                body: new FormData(messageForm),
            });
            showMessages(data.messages);
            messageForm.reset();
            status.textContent = 'Message sent.';
        } catch (error) {
            status.textContent = error.message;
        } finally {
            button.disabled = false;
        }
    });

    request(widget.dataset.stateUrl)
        .then((data) => {
            if (data.active) showActiveChat(data.messages);
        })
        .catch((error) => {
            status.textContent = error.message;
        });
})();
