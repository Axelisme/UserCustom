-- Keymaps are automatically loaded on the VeryLazy event
-- Default keymaps that are always set: https://github.com/LazyVim/LazyVim/blob/main/lua/lazyvim/config/keymaps.lua
-- Add any additional keymaps here

-- Let <C-c> work like <Esc> in normal mode
vim.keymap.set({ "i", "s" }, "<C-c>", "<C-[>", { remap = true })

-- Navigate in insert mode by Ctrl-hjkl
vim.keymap.set("i", "<c-h>", "<Left>")
vim.keymap.set("i", "<c-j>", "<Down>")
vim.keymap.set("i", "<c-k>", "<Up>")
vim.keymap.set("i", "<c-l>", "<Right>")

-- cd to the directory of the current file
vim.keymap.set("n", "<leader>;", ":cd %:p:h<CR>:pwd<CR>", { desc = "Cd to current file directory" })
