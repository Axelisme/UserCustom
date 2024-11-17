return {
  {
    -- let mamba env can be find by venv-selector.nvim
    "linux-cultist/venv-selector.nvim",
    branch = "regexp",
    -- enabled = false,
    optional = true,
    opts = {
      settings = {
        search = {
          cwd = false,
          workspace = false,
          micromamba_envs = {
            command = "$FD 'bin/python$' $HOME/micromamba/envs --full-path --color never",
            on_telescope_result_callback = function(filepath)
              return vim.fs.basename(filepath:gsub("/bin/python", ""))
            end,
            type = "anaconda",
          },
        },
      },
    },
  },
  {
    "lualine.nvim",
    optional = true,
    opts = function(_, opts)
      table.insert(opts.sections.lualine_y, {
        function()
          local venv = os.getenv("CONDA_PREFIX")
          if venv ~= nil and string.find(venv, "/") then
            local orig_venv = venv
            for w in orig_venv:gmatch("([^/]+)") do
              venv = w
            end
            -- venv = string.format("%s", venv)
          end
          return " " .. (venv or "NO ENV")
        end,
        cond = function()
          return vim.bo.filetype == "python"
        end,
      })
    end,
  },
  {
    "neovim/nvim-lspconfig",
    optional = true,
    opts = {
      servers = {
        basedpyright = {
          settings = {
            pyright = {
              -- Using Ruff's import organizer
              disableOrganizeImports = true,
            },
            basedpyright = {
              analysis = {
                ignore = { "*" }, -- Use Ruff
                -- Basic type checking
                typeCheckingMode = "basic",
                autoImportCompletions = false,
              },
            },
          },
        },
      },
    },
  },
  {
    "benlubas/molten-nvim",
    build = ":UpdateRemotePlugins",
    dependencies = { "image.nvim" },
    keys = {
      { "<localleader>mi", "<cmd>MoltenInit<CR>", desc = "Initialize the plugin" },
      { "<localleader>ml", "<cmd>MoltenEvaluateLine<CR>", desc = "Evaluate line" },
    },
    config = function()
      vim.g.molten_image_provider = "image.nvim"

      local function map(mode, key, cmd, desc)
        vim.keymap.set(mode, key, cmd, { silent = true, desc = desc })
      end
      map("n", "<localleader>mr", ":MoltenReevalCell<CR>", "Re-evaluate cell")
      map("n", "<localleader>md", ":MoltenDelete<CR>", "Delete cell")
      map("n", "<localleader>mh", ":MoltenHideOutput<CR>", "Hide output")
      map("n", "<localleader>mo", ":noautocmd MoltenEnterOutput<CR>", "Open output")
      map("n", "<S-CR>", function()
        local function is_cell_delimiter(bufnr, line_num)
          local line = vim.api.nvim_buf_get_lines(bufnr, line_num, line_num + 1, false)[1]
          return line:find("# %%") ~= nil
        end
        -- Helper function to check if a line is non-empty
        local function is_non_empty_line(bufnr, line_num)
          local line = vim.api.nvim_buf_get_lines(bufnr, line_num, line_num + 1, false)[1]
          return line:find("%S") ~= nil
        end
        -- Find the start of the current cell
        local function find_cell_start(bufnr, current_line)
          local start_line = current_line

          while start_line > 0 do
            if is_cell_delimiter(bufnr, start_line) then
              return start_line
            end
            start_line = start_line - 1
          end

          return nil
        end
        -- Find the end of the current cell
        local function find_cell_end(bufnr, start_line)
          local end_line = start_line
          local last_non_empty = start_line
          local max_line = vim.api.nvim_buf_line_count(bufnr) - 1

          while end_line < max_line do
            end_line = end_line + 1

            if is_non_empty_line(bufnr, end_line) then
              last_non_empty = end_line
            end

            if is_cell_delimiter(bufnr, end_line) then
              return last_non_empty
            end
          end

          return last_non_empty
        end
        local original_pos = vim.api.nvim_win_get_cursor(0)
        local current_line = original_pos[1] - 1

        -- Find cell boundaries
        local start_line = find_cell_start(0, current_line)
        if not start_line then
          Snacks.notify("No cell delimiter found before cursor")
          return
        end

        local end_line = find_cell_end(0, start_line)

        if start_line == end_line then
          Snacks.notify("No cell delimiter found after cursor")
          return
        end

        -- Move cursor and make selection
        vim.api.nvim_win_set_cursor(0, { start_line + 1, 0 })
        vim.cmd(string.format("normal! V%dG", end_line + 1))
        vim.api.nvim_feedkeys(vim.api.nvim_replace_termcodes("<Esc>", false, true, true), "nx", false)
        vim.cmd("MoltenEvaluateVisual")
      end, "Evaluate Block")
    end,
  },
}
