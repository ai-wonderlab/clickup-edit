"""Test sequential execution mode."""

import pytest
from src.core.refiner import Refiner


class TestSequentialMode:
    """Test cases for sequential execution."""
    
    def test_parse_simple_request_no_split(self):
        """Single operation should return single step."""
        refiner = Refiner(None, None, None)
        
        request = "αλλαξε το 20% σε 30%. Όλα τα υπολοιπα να μεινουνε ακριβως ιδια"
        
        steps = refiner.parse_request_into_steps(request)
        
        assert len(steps) == 1
        assert steps[0] == "αλλαξε το 20% σε 30%. Όλα τα υπολοιπα να μεινουνε ακριβως ιδια"
    
    def test_parse_complex_request_with_commas(self):
        """Multiple operations separated by commas."""
        refiner = Refiner(None, None, None)
        
        request = "βαλε το λογοτυπο δεξια τελειως, αλλαξε το 20% σε 30%, γραψε FREDDO. Όλα τα υπολοιπα να μεινουνε ακριβως ιδια"
        
        steps = refiner.parse_request_into_steps(request)
        
        assert len(steps) == 3
        assert steps[0] == "βαλε το λογοτυπο δεξια τελειως. Όλα τα υπολοιπα να μεινουνε ακριβως ιδια"
        assert steps[1] == "αλλαξε το 20% σε 30%. Όλα τα υπολοιπα να μεινουνε ακριβως ιδια"
        assert steps[2] == "γραψε FREDDO. Όλα τα υπολοιπα να μεινουνε ακριβως ιδια"
    
    def test_parse_complex_request_with_kai(self):
        """Multiple operations separated by 'και' (Greek and)."""
        refiner = Refiner(None, None, None)
        
        request = "βαλε το λογοτυπο δεξια και αλλαξε το 20% σε 30% και γραψε FREDDO. Όλα τα υπολοιπα να μεινουνε ακριβως ιδια"
        
        steps = refiner.parse_request_into_steps(request)
        
        assert len(steps) == 3
        assert steps[0] == "βαλε το λογοτυπο δεξια. Όλα τα υπολοιπα να μεινουνε ακριβως ιδια"
        assert steps[1] == "αλλαξε το 20% σε 30%. Όλα τα υπολοιπα να μεινουνε ακριβως ιδια"
        assert steps[2] == "γραψε FREDDO. Όλα τα υπολοιπα να μεινουνε ακριβως ιδια"
    
    def test_parse_mixed_delimiters(self):
        """Mix of commas and 'και'."""
        refiner = Refiner(None, None, None)
        
        request = "βαλε λογοτυπο, αλλαξε 20% και γραψε FREDDO. Όλα τα υπολοιπα να μεινουνε ακριβως ιδια"
        
        steps = refiner.parse_request_into_steps(request)
        
        assert len(steps) == 3
        assert all("Όλα τα υπολοιπα" in step for step in steps)
    
    def test_parse_no_preservation_clause(self):
        """Request without preservation clause adds default."""
        refiner = Refiner(None, None, None)
        
        request = "βαλε λογοτυπο δεξια, αλλαξε 20%"
        
        steps = refiner.parse_request_into_steps(request)
        
        assert len(steps) == 2
        assert steps[0] == "βαλε λογοτυπο δεξια. Όλα τα υπολοιπα να μεινουνε ακριβως ιδια"
        assert steps[1] == "αλλαξε 20%. Όλα τα υπολοιπα να μεινουνε ακριβως ιδια"
    
    def test_parse_preserves_custom_clause(self):
        """Custom preservation clause is preserved."""
        refiner = Refiner(None, None, None)
        
        request = "βαλε λογοτυπο, αλλαξε 20%. Όλα τα υπολοιπα να μεινουνε ιδια εκτος απο το χρωμα"
        
        steps = refiner.parse_request_into_steps(request)
        
        assert len(steps) == 2
        assert "Όλα τα υπολοιπα να μεινουνε ιδια εκτος απο το χρωμα" in steps[0]
        assert "Όλα τα υπολοιπα να μεινουνε ιδια εκτος απο το χρωμα" in steps[1]
    
    def test_parse_empty_operations_filtered(self):
        """Empty operations from multiple commas are filtered."""
        refiner = Refiner(None, None, None)
        
        request = "βαλε λογοτυπο,, αλλαξε 20%,,,. Όλα τα υπολοιπα να μεινουνε ακριβως ιδια"
        
        steps = refiner.parse_request_into_steps(request)
        
        assert len(steps) == 2  # Only 2 valid operations


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
