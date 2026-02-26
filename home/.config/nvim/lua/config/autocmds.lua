-- Autocmds are automatically loaded on the VeryLazy event
-- Default autocmds that are always set: https://github.com/LazyVim/LazyVim/blob/main/lua/lazyvim/config/autocmds.lua
-- Add any additional autocmds here

local augroup = vim.api.nvim_create_augroup
local autocmd = vim.api.nvim_create_autocmd

if vim.g.vscode then
  return
end

-- Don't continue comments with o and O
autocmd("BufEnter", {
  pattern = { "*" },
  callback = function()
    vim.opt.formatoptions:remove({ "c", "r", "o" })
  end,
  group = augroup("no_comment_continue", { clear = true }),
  desc = "Don't new line comments",
})

-- Enable <C-l> in terminal
autocmd("TermOpen", {
  desc = "Enable <C-l> in terminal",
  callback = function(ev)
    vim.keymap.set("t", "<C-l>", "<C-l>", { buffer = ev.buf, nowait = true })
  end,
})
