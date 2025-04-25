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

-- vscode
if vim.g.vscode then -- VSCode extension
  local vscode = require("vscode-neovim")
  local function map(mode, lhs, rhs)
    vim.keymap.set(mode, lhs, function()
      vscode.call(rhs)
    end, { silent = true, noremap = true })
  end

  -- Remap folding keys
  map("n", "zM", "editor.foldAll")
  map("n", "zR", "editor.unfoldAll")
  map("n", "zc", "editor.fold")
  map("n", "zC", "editor.foldRecursively")
  map("n", "zo", "editor.unfold")
  map("n", "zO", "editor.unfoldRecursively")
  map("n", "za", "editor.toggleFold")

  -- Remap move keys
  local function mapMove(key, direction)
    -- print("Mapping move key: ", key, direction)
    vim.keymap.set("n", key, function()
      local count = vim.v.count
      local v = 1
      local style = "wrappedLine"
      if count > 0 then
        v = count
        style = "line"
      end
      vscode.action("cursorMove", {
        args = {
          to = direction,
          by = style,
          value = v,
        },
      })
    end)
  end
  mapMove("k", "up")
  mapMove("j", "down")
end
