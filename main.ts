import {
	App,
	Plugin,
	TFile,
	Notice,
	PluginSettingTab,
	Setting,
} from "obsidian";
import * as path from "path";
import * as fs from "fs";
import { lock, unlock } from 'proper-lockfile';

interface RagChatPluginSettings {
	chatFolderName: string;
}

const DEFAULT_SETTINGS: RagChatPluginSettings = {
	chatFolderName: "RAG Chats",
};

export default class RagChatPlugin extends Plugin {
	settings: RagChatPluginSettings;

	async onload() {
		await this.loadSettings();

		this.addCommand({
			id: "open-rag-chat",
			name: "Open RAG Chat",
			callback: () => this.openRagChat(),
		});

		this.registerMarkdownPostProcessor((el, ctx) => {
			const formEl = el.querySelector("#chat-form");
			if (formEl) {
				formEl.addEventListener("submit", (e) => {
					e.preventDefault();
					const input = formEl.querySelector("input") as HTMLInputElement;
					console.log(input.value);
					if (input) {
						this.handleQuestionSubmit(input.value, ctx.sourcePath);
						input.value = ""; // Clear input after submission
					}
				});
			}
		});

		this.addSettingTab(new RagChatSettingTab(this.app, this));
	}

	async loadSettings() {
		this.settings = Object.assign(
			{},
			DEFAULT_SETTINGS,
			await this.loadData()
		);
	}

	async saveSettings() {
		await this.saveData(this.settings);
	}

	async openRagChat() {
		const vault = this.app.vault;
		const chatFolder = vault.getAbstractFileByPath(this.settings.chatFolderName);

		if (!chatFolder) {
			await vault.createFolder(this.settings.chatFolderName);
		}

		const newChatFile = `${this.settings.chatFolderName}/${Date.now()}.md`;
		const file = await vault.create(newChatFile, this.getInitialContent());

		this.app.workspace.getLeaf().openFile(file);
	}

	getInitialContent(): string {
		return `
<div id="chat-log" style="margin-bottom: 10px;"></div>

<form id="chat-form">
  <div style="display: flex; flex-direction: row; align-items: center;">
    <input type="text" placeholder="Ask a question" style="flex: 1;">
    <button type="submit" style="margin-left:10px;">Submit</button>
  </div>
</form>

---
`;
	}

	async handleQuestionSubmit(question: string, filePath: string) {
		const jsonPath = path.join(
			(this.app.vault.adapter as any).basePath,
			".obsidian/plugins/obsidian-sample-plugin/rag_question.json"
		);

		try {
			// Check if file exists; create it if it doesn't
			if (!fs.existsSync(jsonPath)) {
				const questionData = { question: question }; // Initialize with the question
				fs.writeFileSync(jsonPath, JSON.stringify(questionData, null, 2));
				console.log("Question JSON file created successfully.");
			}

			// Lock the file
			await lock(jsonPath);

			// Read and update the question in the file
			let existingData = { question: "" }; // Default structure

			try {
				const fileContent = fs.readFileSync(jsonPath, "utf8");
				if (fileContent) {
					existingData = JSON.parse(fileContent);
				}
			} catch (parseError) {
				console.error("Error parsing JSON, initializing with default:", parseError);
			}

			// Update the question
			existingData.question = question;
			fs.writeFileSync(jsonPath, JSON.stringify(existingData, null, 2));

			// Call to render results after submitting question
			const file = this.app.vault.getAbstractFileByPath(filePath) as TFile;
			await this.renderResultsWhenAvailable(file, question);
			
		} catch (error) {
			console.error("Error handling question:", error);
			new Notice("Failed to process the question. Please try again.");
		} finally {
			// Unlock the file
			await unlock(jsonPath);
		}
	}

	async renderResultsWhenAvailable(file: TFile, question: string) {
		const resultsPath = path.join(
			(this.app.vault.adapter as any).basePath,
			".obsidian/plugins/obsidian-sample-plugin/rag_results.json"
		);
		const maxRetries = 30; // Maximum number of retries
		const retryInterval = 2000; // 2 seconds between retries
	
		const checkResults = async (retryCount: number) => {
			if (retryCount >= maxRetries) {
				console.error("Max retries reached. No results available.");
				new Notice("Failed to get results. Please try again.");
				return;
			}
	
			if (fs.existsSync(resultsPath)) {
				try {
					await lock(resultsPath);
	
					const resultsData = JSON.parse(fs.readFileSync(resultsPath, "utf8"));
	
					const answer = resultsData.answer || "No answer provided";
					const sources = resultsData.sources || [];
	
					const sourcesText = sources.length > 0
						? sources.map((item: string) => {
							const sourceName = path.basename(item, path.extname(item));
							return `- [[${sourceName}]]`;
						}).join("\n")
						: "- No sources found.";
	
					const answerContent = `## ${question}\n\n${answer}\n\n### Sources:\n${sourcesText}\n\n---\n\n`;
	
					const currentContent = await this.app.vault.read(file);
					const [header, ...rest] = currentContent.split('---');
					const newContent = `${header.trim()}\n\n---\n\n${answerContent}${rest.join('---').trim()}`;
	
					await this.app.vault.modify(file, newContent);
	
					const updatedContent = await this.app.vault.read(file);
					if (updatedContent.includes(answerContent)) {
						console.log("Content updated successfully.");
						new Notice("Response rendered successfully.");
					} else {
						console.error("Failed to verify content update.");
						new Notice("Failed to render the response. Retrying...");
						setTimeout(() => checkResults(retryCount + 1), retryInterval);
					}
				} catch (error) {
					console.error("Error processing results:", error);
				} finally {
					await unlock(resultsPath);
					fs.unlink(resultsPath, (err) => {
						if (err) {
							console.error("Error deleting file:", err);
						} else {
							console.log("Results file deleted successfully");
						}
					});
				}
			} else {
				console.log(`Retrying to fetch results (${retryCount + 1}/${maxRetries})...`);
				setTimeout(() => checkResults(retryCount + 1), retryInterval);
			}
		};
	
		checkResults(0);
	}
}

class RagChatSettingTab extends PluginSettingTab {
	plugin: RagChatPlugin;

	constructor(app: App, plugin: RagChatPlugin) {
		super(app, plugin);
		this.plugin = plugin;
	}

	display(): void {
		let { containerEl } = this;
		containerEl.empty();
		containerEl.createEl("h2", { text: "RAG Chat Settings" });

		new Setting(containerEl)
			.setName("Chat Folder Name")
			.setDesc("The folder where chat files will be stored")
			.addText((text) =>
				text
					.setPlaceholder("Enter folder name")
					.setValue(this.plugin.settings.chatFolderName)
					.onChange(async (value: string) => {
						this.plugin.settings.chatFolderName = value;
						await this.plugin.saveSettings();
					})
			);
	}
}
