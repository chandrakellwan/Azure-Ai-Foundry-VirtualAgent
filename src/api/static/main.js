// Copyright (c) Microsoft. All rights reserved.
// Licensed under the MIT license. See LICENSE.md file in the project root for full license information.

import ChatUI from './ChatUI.js';
import ChatClient from './ChatClient.js';

function initChat() {
    const chatUI = new ChatUI();
    const chatClient = new ChatClient(chatUI);

    const form = document.getElementById("chat-form");
    const messageInput = document.getElementById("message");
    const targetContainer = document.getElementById("messages");
    const placeholderWrapper = document.getElementById("placeholder-wrapper");

    form.addEventListener("submit", async function(e) {
        e.preventDefault();
        
        // Remove placeholder message if it exists
        if (placeholderWrapper) {
            placeholderWrapper.remove();
        }

        await chatClient.sendMessage("/chat", messageInput.value.trim());
        messageInput.value = "";
    });

    window.onbeforeunload = function() {
        chatClient.closeEventSource();
    };
}

document.addEventListener("DOMContentLoaded", initChat);