return {
  {
    -- let mamba env can be find by venv-selector.nvim
    "linux-cultist/venv-selector.nvim",
    branch = "regexp",
    -- enabled = false,
    dependencies = { "nvim-telescope/telescope.nvim", lazy = true },
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
}
