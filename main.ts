import { App, ItemView, WorkspaceLeaf, Plugin, TFile, MarkdownRenderer } from 'obsidian';
import { request } from 'obsidian';

const VIEW_TYPE_CHAT = 'chat-view';

interface ChatMessage {
    text: string;
    isUser: boolean;
    sources?: string[];
}

interface ApiResponse {
    answer: string;
    query: string;
    sources: string[];
}

export default class ChatPlugin extends Plugin {
    async onload() {
        this.registerView(VIEW_TYPE_CHAT, (leaf) => new ChatView(leaf, this.app));

        this.addRibbonIcon('message-square', 'Open Chat Panel', async () => {
            const leaves = this.app.workspace.getLeavesOfType(VIEW_TYPE_CHAT);
            if (leaves.length === 0) {
                await this.app.workspace.getRightLeaf(false).setViewState({
                    type: VIEW_TYPE_CHAT,
                });
            }
            this.app.workspace.revealLeaf(
                this.app.workspace.getLeavesOfType(VIEW_TYPE_CHAT)[0]
            );
        });

        // Load the CSS
        this.loadStyles();
    }

    onunload() {
        this.app.workspace.detachLeavesOfType(VIEW_TYPE_CHAT);
    }

    loadStyles() {
        const styleEl = document.createElement('link');
        styleEl.rel = 'stylesheet';
        styleEl.href = 'styles.css';
        document.head.appendChild(styleEl);
    }
}

class ChatView extends ItemView {
    messages: ChatMessage[] = [];
    chatContainer: HTMLElement;
    inputContainer: HTMLElement;
    chatInput: HTMLTextAreaElement;
    sendButton: HTMLButtonElement;
    exportButton: HTMLButtonElement;
    app: App;

    constructor(leaf: WorkspaceLeaf, app: App) {
        super(leaf);
        this.app = app;
    }

    getViewType() {
        return VIEW_TYPE_CHAT;
    }

    getDisplayText() {
        return 'Chat Interface';
    }

    async onOpen() {
        const container = this.containerEl.children[1];
        container.empty();
        container.addClass('chat-view-container');

        this.chatContainer = container.createEl('div', { cls: 'chat-messages' });
        this.inputContainer = container.createEl('div', { cls: 'chat-input-container' });

        this.chatInput = this.inputContainer.createEl('textarea', {
            cls: 'chat-input',
            attr: { placeholder: 'Type your message...' }
        });

        this.sendButton = this.inputContainer.createEl('button', { text: 'Send', cls: 'chat-send-button' });
        this.exportButton = this.inputContainer.createEl('button', { text: 'Export', cls: 'chat-export-button' });

        this.sendButton.onclick = () => this.sendMessage(this.chatInput.value);
        this.exportButton.onclick = () => this.exportChat();
        this.chatInput.onkeydown = (event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                this.sendMessage(this.chatInput.value);
            }
        };
    }

    async sendMessage(text: string) {
        if (text.trim() === '') return;
        
        this.addMessage({ text, isUser: true });
        this.chatInput.value = '';
        
        // Disable input and buttons
        this.setInputState(false);
        
        try {
            const response = await this.makeApiRequest(text);
            this.addMessage({ text: response.answer, isUser: false, sources: response.sources });
        } catch (error) {
            console.error('Error making API request:', error);
            this.addMessage({ text: "Sorry, there was an error processing your request.", isUser: false });
        } finally {
            // Re-enable input and buttons
            this.setInputState(true);
        }
    }

    setInputState(enabled: boolean) {
        this.chatInput.disabled = !enabled;
        this.sendButton.disabled = !enabled;
        this.exportButton.disabled = !enabled;
    }

    async makeApiRequest(query: string): Promise<ApiResponse> {
        const response = await request({
            url: 'http://localhost:5000/arraysum',
            method: 'POST',
            body: JSON.stringify({ query }),
            headers: { 'Content-Type': 'application/json' }
        });

        return JSON.parse(response);
    }

    addMessage(message: ChatMessage) {
        this.messages.push(message);
        this.renderMessage(message);
        this.chatContainer.scrollTop = this.chatContainer.scrollHeight;
    }

    async renderMessage(message: ChatMessage) {
        const messageEl = this.chatContainer.createEl('div', {
            cls: `chat-message ${message.isUser ? 'user-message' : 'bot-message'}`
        });

        if (message.isUser) {
            messageEl.createEl('p', { text: message.text });
        } else {
            const contentEl = messageEl.createEl('div');
            await MarkdownRenderer.renderMarkdown(message.text, contentEl, '', this);
        }

        if (message.sources && message.sources.length > 0) {
            const sourcesEl = messageEl.createEl('div', { cls: 'message-sources' });
            sourcesEl.createEl('p', { text: 'Sources:', cls: 'sources-header' });
            const sourcesList = sourcesEl.createEl('ul');
            message.sources.forEach(source => {
                const listItem = sourcesList.createEl('li');
                const link = this.formatSourceAsLink(source);
                listItem.createEl('span', {
                    text: link,
                    cls: 'internal-link'
                });
            });
        }
    }

    formatSourceAsLink(source: string): string {
        const linkText = source.replace(/\.[^/.]+$/, "");
        const normalizedPath = linkText.replace(/\\/g, '/');
        const fileName = normalizedPath.substring(normalizedPath.lastIndexOf('/') + 1);
        return `[[${normalizedPath} | ${fileName}]]`;
    }

    async exportChat() {
        if (this.messages.length === 0) return;

        const chatContent = this.messages.map((m, index) => {
            let content = '';
            if (m.isUser) {
                content += `## ${m.text}\n`;
            } else {
                content += `${m.text}\n\n`;
                if (m.sources && m.sources.length > 0) {
                    content += 'Sources:\n' + m.sources.map(s => `- ${this.formatSourceAsLink(s)}`).join('\n') + '\n\n';
                    content+="\n\n---\n"
                }
            }

            if (index < this.messages.length - 1) {
                content += '\n';
            }
            return content;
        }).join('');

        const fileName = `chat-export-${new Date().toISOString().replace(/:/g, '-')}.md`;
        const folderPath = 'chats';

        try {
            const folder = this.app.vault.getAbstractFileByPath(folderPath);
            if (!folder) {
                await this.app.vault.createFolder(folderPath);
            }

            await this.app.vault.create(`${folderPath}/${fileName}`, chatContent);
            console.log('Chat exported successfully');
        } catch (error) {
            console.error('Error exporting chat:', error);
        }
    }

    async onClose() {
        // Any cleanup code can go here
    }
}