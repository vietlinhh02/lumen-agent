import pytest
import uuid
import json
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.assistant.deep_research_worker import run_deep_research

@pytest.mark.asyncio
async def test_run_deep_research_worker():
    job_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    query = "test"

    # We mock everything since we just want to ensure pipeline sequential structure (TDD)
    with patch("app.services.assistant.deep_research_worker.async_session_factory") as mock_db_factory:
        mock_db = AsyncMock()
        mock_db_factory.return_value.__aenter__.return_value = mock_db
        
        # User exists
        mock_db.scalar.return_value = MagicMock()
        
        with patch("app.services.assistant.deep_research_worker._update_job_progress", new_callable=AsyncMock) as mock_update:
            with patch("app.services.assistant.deep_research_worker._search_web_impl", new_callable=AsyncMock) as mock_search:
                mock_search.return_value = {"papers": [{"id": "p1"}, {"id": "p2"}]}
                
                with patch("app.services.assistant.deep_research_worker._save_paper_impl", new_callable=AsyncMock) as mock_save:
                    mock_save.return_value = {"status": "success"}
                    
                    with patch("app.services.assistant.deep_research_worker._generate_matrix_impl", new_callable=AsyncMock) as mock_matrix:
                        mock_matrix.return_value = {"status": "success"}
                        
                        with patch("app.services.assistant.deep_research_worker._detect_gaps_impl", new_callable=AsyncMock) as mock_gap:
                            mock_gap.return_value = {"status": "success"}
                            
                            with patch("app.services.assistant.deep_research_worker._generate_report_impl", new_callable=AsyncMock) as mock_report:
                                mock_report.return_value = {"status": "success"}
                                
                                await run_deep_research(job_id, project_id, user_id, query)
                                
                                # Assert Pipeline Called Correctly
                                mock_search.assert_called_once()
                                assert mock_save.call_count == 2
                                mock_matrix.assert_called_once()
                                mock_gap.assert_called_once()
                                mock_report.assert_called_once()
