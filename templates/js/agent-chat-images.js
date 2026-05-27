// Agent chat image handling
// Extracted from templates/index.html
        function renderPendingChatImages() {
            if (!chatImagePreviews) return;
            chatImagePreviews.innerHTML = '';
            pendingChatImages.forEach((dataUrl, idx) => {
                const wrap = document.createElement('div');
                wrap.className = 'chat-image-preview';
                wrap.innerHTML = `<img src="${dataUrl}" alt="preview"><button class="remove-btn" title="Remove">&times;</button>`;
                wrap.querySelector('.remove-btn').addEventListener('click', () => {
                    pendingChatImages.splice(idx, 1);
                    renderPendingChatImages();
                });
                chatImagePreviews.appendChild(wrap);
            });
        }

        function addChatImage(file) {
            if (!file || !file.type.startsWith('image/')) return;
            const reader = new FileReader();
            reader.onload = (e) => {
                pendingChatImages.push(e.target.result);
                renderPendingChatImages();
            };
            reader.readAsDataURL(file);
        }
