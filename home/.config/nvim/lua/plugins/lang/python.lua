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
        options = {
          debug = true,
          activate_venv_in_terminal = true,
          set_environment_variables = true,
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
    cmd = "MoltenInit",
    dependencies = { "image.nvim" },
    keys = {
      { "<localleader>mi", ":MoltenInit<CR>", { silent = true, desc = "Initialize the plugin" } },
      { "<localleader>ml", ":MoltenEvaluateLine<CR>", { silent = true, desc = "Evaluate line" } },
      { "<localleader>ms", ":<C-u>MoltenEvaluateVisual<CR>gv<esc>", { silent = true, desc = "Evaluate selection" } },
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
    end,
  },
}
