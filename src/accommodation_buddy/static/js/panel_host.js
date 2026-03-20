function panelHost() {
    return {
        init() {
            // Make panels draggable for reordering (via header only)
            this.initDragAndDrop();
        },

        initDragAndDrop() {
            const sidebar = document.querySelector('.plugin-sidebar');
            if (!sidebar) return;

            let draggedEl = null;

            sidebar.querySelectorAll('.plugin-panel').forEach(panel => {
                const header = panel.querySelector('.panel-header');
                if (!header) return;

                // Only the header initiates drag — content remains selectable
                header.draggable = true;

                header.addEventListener('dragstart', (e) => {
                    draggedEl = panel;
                    panel.classList.add('dragging');
                    e.dataTransfer.effectAllowed = 'move';
                });

                header.addEventListener('dragend', () => {
                    panel.classList.remove('dragging');
                    draggedEl = null;
                    sidebar.querySelectorAll('.plugin-panel').forEach(p => p.classList.remove('drag-over'));
                });

                panel.addEventListener('dragover', (e) => {
                    e.preventDefault();
                    e.dataTransfer.dropEffect = 'move';
                    if (draggedEl && draggedEl !== panel) {
                        panel.classList.add('drag-over');
                    }
                });

                panel.addEventListener('dragleave', () => {
                    panel.classList.remove('drag-over');
                });

                panel.addEventListener('drop', (e) => {
                    e.preventDefault();
                    panel.classList.remove('drag-over');
                    if (draggedEl && draggedEl !== panel) {
                        const allPanels = [...sidebar.querySelectorAll('.plugin-panel')];
                        const fromIndex = allPanels.indexOf(draggedEl);
                        const toIndex = allPanels.indexOf(panel);
                        if (fromIndex < toIndex) {
                            panel.after(draggedEl);
                        } else {
                            panel.before(draggedEl);
                        }
                    }
                });
            });
        }
    };
}
